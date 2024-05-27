import asyncio
import base64
import urllib
import websockets
import os
import cv2
import face_recognition
import numpy as np
import requests
import json

modeType = 0
counter = 0
folderPath = 'Images'
FaceDb = {}
imgStudent = []
url = 'http://localhost:5000'
Cookie = ''


def Authenticate(pswd, mail):
    global Cookie
    myobj = {'email': str(mail),
             'password': str(pswd)}
    x = requests.post(url + "/auth/login", json=myobj)
    Cookie = {'academiqa': json.loads(x.text)['accessToken']}
    print(Cookie)


def GetStudentList(id):
    global Cookie
    x = requests.get(url + "/session/absentStudents/"+str(id), headers={'Authorization':  "Bearer " + Cookie['academiqa']})
    print(json.loads(x.text))
    return json.loads(x.text)


def RegisterStudent(SessionId, id):
    myobj = {'session': {'id': str(SessionId)},
             'student': {'id': str(id)}}
    x = requests.post(url + "/presence", json=myobj, headers={'Authorization':  "Bearer " + Cookie['academiqa']})


def FetchFaces(SessionId):
    global FaceDb
    if SessionId in FaceDb.keys():
        print(SessionId, "Has been already fetched")
        return
    FaceDb[SessionId] = []
    # fetch student ids from database
    students = GetStudentList(SessionId)
    #students = [55864, 313567]
    # Register faces into a shared dict
    for student in students:
        if student['photo'] is not None:
            try:
                resp = requests.get(student['photo'], stream=True).content
                image = np.asarray(bytearray(resp), dtype="uint8")
                image = cv2.imdecode(image, cv2.IMREAD_COLOR)
                encode = face_recognition.face_encodings(image)[0]
                FaceDb[SessionId].append([encode, [student["id"], student["username"]]])
                print("fetched id:", student["id"])
            except Exception as e:
                print(e)
                print('Error fetching student : ', student)
    print("Finished Fetching SessionId: ", SessionId)



async def websocket_listener(websocket, path):
    global modeType, counter, imgStudent, FaceDb
    # This function will be called whenever a new WebSocket connection is established
    print(f"New connection established: {websocket.remote_address}")
    SessionId = -1
    tries = 0
    try:
        # SessionId fetching
        while True:
            if tries == 3:
                return
            message = str(await websocket.recv())
            tries += 1
            if message.startswith("S"):
                SessionId = int(message[1:])
                # check if session id exists and fetch faces
                break
            else:
                await websocket.send(str(3))
        if SessionId is None:
            await websocket.send(str(2))
            return
        FetchFaces(SessionId)
        await websocket.send(str(0))
        encodeListKnown = []
        studentIds = []
        for sessionparticipant in FaceDb[SessionId]:
            encodeListKnown.append(sessionparticipant[0])
            studentIds.append(sessionparticipant[1])
        print(studentIds)
        print(encodeListKnown)
        if len(studentIds) == 0:
            await websocket.send(str(1))
        # Face Detection
        while True:
            # Receive message from the client
            message = await websocket.recv()
            prefix_to_remove = "data:image/jpeg;base64,"
            if message == "null":
                print("comment")
                await websocket.send(str(0))
                continue
            if message.startswith(prefix_to_remove):
                # Remove the prefix
                message = message[len(prefix_to_remove):]
            decoded_data = base64.b64decode(message)
            nparr = np.frombuffer(decoded_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            matched = False
            try:
                if img.size == 0:
                    print("Error: Empty frame received from the webcam.")
                    return
            except Exception as e:
                print(e)
                return
            imgS = cv2.resize(img, (0, 0), None, 0.25, 0.25)
            imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)
            faceCurFrame = face_recognition.face_locations(imgS)
            encodeCurFrame = face_recognition.face_encodings(imgS, faceCurFrame)
            if faceCurFrame:
                for encodeFace, faceLoc in zip(encodeCurFrame, faceCurFrame):
                    matches = face_recognition.compare_faces(encodeListKnown, encodeFace)
                    cntr = 0
                    # print("Match Index", matchIndex)
                    deleteSchedule= []

                    for match in matches:
                        if match:
                            # print("Known Face Detected")
                            data = {
                                'id': studentIds[cntr][0],
                                'username': studentIds[cntr][1]
                            }
                            await websocket.send(json.dumps(data))
                            matched = True
                            print(studentIds[cntr])
                            # report as present
                            RegisterStudent(SessionId, studentIds[cntr][0])
                            deleteSchedule.append(cntr)
                            if len(studentIds)-len(deleteSchedule) == 0:
                                await websocket.send(str(1))
                                del FaceDb[SessionId]
                                return
                        cntr += 1
                    for delete in deleteSchedule:
                        del studentIds[delete]
                        del encodeListKnown[delete]
                    deleteSchedule = []
            if not matched:
                await websocket.send(str(0))
    except websockets.exceptions.ConnectionClosedError:
        if(SessionId is not None):
            del FaceDb[SessionId]
        print(f"Connection closed by client: {websocket.remote_address}")
    except Exception as e:
        print(e)
        if (SessionId is not None):
            del FaceDb[SessionId]


async def main():
    # Start the WebSocket server
    Authenticate('ahmedbensalah@123$', 'ahmedbensalah@example.com')
    server = await websockets.serve(websocket_listener, "localhost", 8765)
    print("WebSocket server started, listening on ws://localhost:8765")
    # Keep the server running until explicitly stopped
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
