CREATE DATABASE smart_evidence;

USE smart_evidence;
GRANT INSERT,SELECT,DELETE,UPDATE ON smart_evidence.* TO 'writer'@'localhost' IDENTIFIED BY 'password';
FLUSH PRIVILEGES;

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT UUID(),
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    rfid_uuid VARCHAR(36) UNIQUE NOT NULL
);
CREATE TABLE lectures (
    lecture_id UUID PRIMARY KEY DEFAULT UUID(),
    name VARCHAR(255) NOT NULL
);
CREATE TABLE user_attendance (
    attendance_id UUID PRIMARY KEY DEFAULT UUID(),
    user_id UUID NOT NULL,
    lecture_id UUID NOT NULL,
    entry_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    leaving_timestamp TIMESTAMP,
    bac DECIMAL(3,2) NOT NULL,
    body_temp DECIMAL(4,2) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (lecture_id) REFERENCES lectures (lecture_id)
);
