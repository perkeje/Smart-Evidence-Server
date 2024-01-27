import signal
import tornado.ioloop
import tornado.web
import tornado.websocket
import MySQLdb as mdb
import sys
import json

active_connections = {
    "evidence": None,
    "user_addition": None,
    "rfid": None
}
temp_user_data = {}
temp_user_attendance_id = None

try:
    db_connection = mdb.connect('localhost', 'writer', 'password', 'smart_evidence')
    print("Successfully connected to MariaDB")
except mdb.Error as e:
    print(f"Error connecting to MariaDB: {e}")
    sys.exit(1)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        try:
            with db_connection.cursor() as cursor:
                # Fetch the latest lecture
                cursor.execute("SELECT lecture_id, name FROM lectures ORDER BY created_at DESC LIMIT 1")
                lecture = cursor.fetchone()

                if lecture:
                    lecture_id, lecture_name = lecture
                    # Fetch user attendance for this lecture
                    cursor.execute("""
                        SELECT ua.attendance_id, u.first_name, u.last_name, ua.entry_timestamp, ua.leaving_timestamp, ua.bac, ua.body_temp
                        FROM user_attendance ua
                        JOIN users u ON ua.user_id = u.user_id
                        WHERE lecture_id = %s
                    """, (lecture_id,))
                    attendance_records = cursor.fetchall()
                else:
                    lecture_name = None
                    attendance_records = []

            self.render("index.html", lecture_name=lecture_name, attendance_records=attendance_records)
        except mdb.Error as e:
            print(f"Database error: {e}")
            self.render("index.html", lecture_name=None, attendance_records=[])

class AddUserHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("add_user.html")

class AddLectureHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("add_lecture.html")

    def post(self):
        lecture_name = self.get_argument("lectureName")

        # Insert lecture into the database
        try:
            with db_connection.cursor() as cursor:
                query = "INSERT INTO lectures (name) VALUES (%s)"
                cursor.execute(query, (lecture_name,))
                db_connection.commit()
                self.redirect("/") 
        except mdb.Error as e:
            self.render("add_lecture.html", error=str(e))


class EvidenceWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        global active_connections
        active_connections["evidence"] = self
        print("Evidence WebSocket opened")

    def on_message(self, message):
        global temp_user_attendance_id
        with db_connection.cursor() as cursor:
            query = "SELECT lecture_id FROM lectures ORDER BY created_at DESC;"
            cursor.execute(query)  
            current_lecture_id = cursor.fetchone()

            if current_lecture_id:
                if message.startswith("#DATA"):
                    data_parts = message[6:].split(", ")  
                    bac = float(data_parts[0].split(":")[1])
                    temp = float(data_parts[1].split(":")[1].replace("}", "").strip())

                    try:
                        if temp_user_attendance_id:

                            query = """
                                INSERT INTO user_attendance 
                                (user_id, lecture_id, bac, body_temp) 
                                VALUES (%s, %s, %s, %s)
                            """
                            cursor.execute(query, (temp_user_attendance_id, current_lecture_id[0], bac, temp))
                            db_connection.commit()

                            cursor.execute("SELECT LAST_INSERT_ID()")
                            last_insert_id = cursor.fetchone()[0]

                            select_query = """
                                SELECT ua.attendance_id, u.first_name, u.last_name, ua.entry_timestamp, ua.leaving_timestamp, ua.bac, ua.body_temp
                                FROM user_attendance ua
                                JOIN users u ON ua.user_id = u.user_id
                                WHERE ua.attendance_id = %s
                            """
                            cursor.execute(select_query, (str(last_insert_id),))
                            last_inserted_record = cursor.fetchone()

                            # Extracting data from the record
                            if last_inserted_record:
                                attendance_id, first_name, last_name, entry_timestamp, leaving_timestamp, bac, temp = last_inserted_record
                                new_attendance_data = {
                                    "id": attendance_id, 
                                    "first_name": first_name, 
                                    "last_name": last_name, 
                                    "entry_timestamp": entry_timestamp.strftime('%Y-%m-%d %H:%M:%S') if entry_timestamp else None,
                                    "leaving_timestamp": leaving_timestamp.strftime('%Y-%m-%d %H:%M:%S') if leaving_timestamp else None,
                                    "bac": bac,
                                    "temp": temp
                                }
                                message = json.dumps(new_attendance_data)
                                EvidenceClientWebSocketHandler.send_updates(message)
                            else:
                                print("No record found for the given attendance ID.")

                    except mdb.Error as e:
                        print(f"Database error: {e}")
                        self.write_message("Error saving attendance data")

                else:
                    rfid_uuid = message.strip()

                    try:
                        query = "SELECT user_id, first_name, last_name FROM users WHERE rfid_uuid = %s"
                        cursor.execute(query, (rfid_uuid,))
                        user = cursor.fetchone()
                        
                        if user:
                            user_id, first_name, last_name = user
                            query = "SELECT attendance_id, leaving_timestamp FROM user_attendance WHERE user_id = %s AND lecture_id = %s;"
                            cursor.execute(query, (user_id, current_lecture_id[0]))
                            current_attendance = cursor.fetchone()

                            if current_attendance:
                                if not current_attendance[1]:
                                    attendance_id = current_attendance[0]  # Assuming this is the ID of the attendance record
                                    try:
                                        with db_connection.cursor() as cursor:
                                            # Update the leaving timestamp for the current attendance record
                                            update_query = "UPDATE user_attendance SET leaving_timestamp = NOW() WHERE attendance_id = %s"
                                            cursor.execute(update_query, (attendance_id,))
                                            db_connection.commit()
                                            self.write_message("Izlaz odobren")
                                    
                                    except mdb.Error as e:
                                        print(f"Database error: {e}")
                                        self.write_message("Error updating attendance record")
                                else:
                                    self.write_message("Ulaz zabranjen") 
                            else:
                                user_name = f"{first_name} {last_name}"
                                temp_user_attendance_id = user_id 
                                
                                self.write_message(user_name)
                        else:
                            self.write_message("Ulaz zabranjen")

                    except mdb.Error as e:
                        print(f"Database error: {e}")
                        self.write_message("Error retrieving user")
            else:
                self.write_message("Ulaz zabranjen") 


    def on_close(self):
        global active_connections
        active_connections["evidence"] = None
        print("Evidence WebSocket closed")

class UserAdditionWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        global active_connections
        active_connections["user_addition"] = self
        print("User Addition WebSocket opened")

    def on_message(self, message):
        # Send this data to ESP8266 to request RFID card UUID
        # Here, you'll need to implement the communication with ESP8266
        global temp_user_data

        # Parse and store the user's name
        user_data = json.loads(message)
        temp_user_data["firstName"] = user_data["firstName"]
        temp_user_data["lastName"] = user_data["lastName"]
        esp_connection = active_connections.get("rfid")  # Assuming 'esp' connection is stored
        if esp_connection:
            print("SENDING TO ESP")
            esp_connection.write_message("#ADD_USER")
        print("Received from client: ", temp_user_data)

    def on_close(self):
        global active_connections
        active_connections["user_addition"] = None
        print("User Addition WebSocket closed")


class RFIDWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True
    

    def open(self):
        global active_connections
        active_connections["rfid"] = self
        print("Rfid WebSocket opened")
    
    def on_message(self, message):
        global temp_user_data

        # Retrieve user's name and RFID UUID
        first_name = temp_user_data.get("firstName", "")
        last_name = temp_user_data.get("lastName", "")
        rfid_uuid = message
         
        # Insert data into the database
        if first_name and last_name:
            try:
                with db_connection.cursor() as cursor:
                    query = "INSERT INTO users (first_name,last_name, rfid_uuid) VALUES (%s, %s, %s);"
                    cursor.execute(query, (first_name,last_name, rfid_uuid))
                    db_connection.commit()
            except mdb.Error as e:
                print(f"Database error: {e}")

        # Clear the temporary data
        temp_user_data.clear()

        # Notify the client
        client = active_connections.get("user_addition")
        if client:
            client.write_message("User Added")

    def on_close(self):
        global active_connections
        active_connections["rfid"] = None
        print("Rfid WebSocket closed")

class EvidenceClientWebSocketHandler(tornado.websocket.WebSocketHandler):
    clients = set()

    def check_origin(self, origin):
        return True

    def open(self):
        EvidenceClientWebSocketHandler.clients.add(self)
        print("New client connected")

    def on_close(self):
        EvidenceClientWebSocketHandler.clients.remove(self)
        print("Client disconnected")

    @classmethod
    def send_updates(cls, message):
        for client in cls.clients:
            try:
                client.write_message(message)
            except:
                print("Error sending message")

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/add_user", AddUserHandler),
        (r"/evidence_ws", EvidenceWebSocketHandler),
        (r"/evidence_client_ws", EvidenceClientWebSocketHandler),
        (r"/user_addition_ws", UserAdditionWebSocketHandler),
        (r"/rfid_ws", RFIDWebSocketHandler),
        (r"/lecture", AddLectureHandler),
    ], static_path="static")

def stop_tornado(signum, frame):
    print("Stopping Tornado app...")
    tornado.ioloop.IOLoop.current().stop()
    quit()

if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    print("Server is running on http://localhost:8888")
    
    signal.signal(signal.SIGINT, stop_tornado)
    
    tornado.ioloop.IOLoop.current().start()
