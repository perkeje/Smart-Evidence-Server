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

try:
    db_connection = mdb.connect('localhost', 'writer', 'password', 'smart_evidence')
    print("Successfully connected to MariaDB")
except mdb.Error as e:
    print(f"Error connecting to MariaDB: {e}")
    sys.exit(1)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class AddUserHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("add_user.html")

class EvidenceWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        global active_connections
        active_connections["evidence"] = self
        print("Evidence WebSocket opened")

    def on_message(self, message):
        # Handle evidence data received from ESP8266
        print("Received from ESP8266: ", message)

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

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/add_user", AddUserHandler),
        (r"/evidence_ws", EvidenceWebSocketHandler),
        (r"/user_addition_ws", UserAdditionWebSocketHandler),
        (r"/rfid_ws", RFIDWebSocketHandler),
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
