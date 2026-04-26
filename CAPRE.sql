CREATE DATABASE capreDB;

USE capreDB;

CREATE TABLE role (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    role_name VARCHAR(50),
    role_level INT NOT NULL
);

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    user_first_name VARCHAR(100) NOT NULL,
    user_middle_name VARCHAR(50),
    user_last_name VARCHAR(100) NOT NULL,
    university_no INT,

    role_id INT NOT NULL,

    FOREIGN KEY(role_id) REFERENCES role(role_id)
);

CREATE TABLE kappa (
    username_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL
);

CREATE TABLE ror (
    password_id INT AUTO_INCREMENT PRIMARY KEY,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE slug (
    username_id INT NOT NULL,
    password_id INT NOT NULL,
    user_id INT NOT NULL,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_current BOOLEAN DEFAULT TRUE,

    PRIMARY KEY (username_id, password_id, user_id),

    FOREIGN KEY (username_id) REFERENCES kappa(username_id),
    FOREIGN KEY (password_id) REFERENCES ror(password_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE login (
    log_in_id INT AUTO_INCREMENT PRIMARY KEY,
    log_in_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    login_device_ip VARCHAR(50),

    user_id INt,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE logout (
    log_out_id INT AUTO_INCREMENT PRIMARY KEY,
    log_in_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    logout_device_ip VARCHAR(50),

    user_id INT,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE signup (
    signup_id INT AUTO_INCREMENT PRIMARY KEY,
    registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,

    user_id INT,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE audit (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    action_type VARCHAR(50),
    affected_table VARCHAR(50),
    affected_record_id INT,
    old_values VARCHAR(100),
    new_values VARCHAR(100),
    action_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    user_id INT,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE contact (
    contact_id INT AUTO_INCREMENT PRIMARY KEY,
    contact_type VARCHAR(50),
    contact_value VARCHAR(100),
    is_primary BOOLEAN,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    user_id INT,

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE program (
    program_id INT AUTO_INCREMENT PRIMARY KEY,
    program_name VARCHAR(50)
);

CREATE TABLE specialization (
    specialization_id INT AUTO_INCREMENT PRIMARY KEY,
    specialization_name VARCHAR(50)
);

CREATE TABLE keyword (
    keyword_id INT AUTO_INCREMENT PRIMARY KEY,
    capstone_keywords VARCHAR(50)
);

CREATE TABLE capstone (
    capstone_id INT AUTO_INCREMENT PRIMARY KEY,
    capstone_title VARCHAR(100),
    capstone_year YEAR,
    capstone_file VARCHAR(255),
    citation_count INT,
    semester VARCHAR(50),
    term VARCHAR(50),

    specialization_id INT,
    program_id INT,
    keyword_id INT

    FOREIGN KEY (specialization_id) REFERENCES specialization(specialization_id),
    FOREIGN KEY (program_id) REFERENCES program(program_id),
    FOREIGN KEY (keyword_id) REFERENCES keyword(keyword_id)
);

CREATE TABLE author (
    author_id INT AUTO_INCREMENT PRIMARY KEY,
    aut_first_name VARCHAR(100),
    aut_middle_name VARCHAR(50),
    aut_last_name VARCHAR(100)
);

CREATE TABLE capAuth (
    capstone_id INT,
    author_id INT,

    role VARCHAR(50),
    author_order INT,

    FOREIGN KEY (capstone_id) REFERENCES capstone(capstone_id),
    FOREIGN KEY (author_id) REFERENCES author(author_id)
);

