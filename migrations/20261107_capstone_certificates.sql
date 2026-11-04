-- Add the diagram's copyright and utilization certificates without changing existing capstones.
BEGIN;

CREATE TABLE copyright (
    copyright_cert_id SERIAL PRIMARY KEY,
    copyright_cert_num VARCHAR(100),
    copyright_cert_date DATE,
    copyright_cert_file TEXT
);

CREATE TABLE utilization (
    utilization_cert_id SERIAL PRIMARY KEY,
    utilization_file TEXT,
    utilization_date DATE
);

ALTER TABLE capstone
    ADD COLUMN copyright_cert_id INT,
    ADD COLUMN utilization_cert_id INT,
    ADD CONSTRAINT capstone_copyright_cert_fk
        FOREIGN KEY (copyright_cert_id) REFERENCES copyright(copyright_cert_id) ON DELETE RESTRICT,
    ADD CONSTRAINT capstone_utilization_cert_fk
        FOREIGN KEY (utilization_cert_id) REFERENCES utilization(utilization_cert_id) ON DELETE RESTRICT,
    ADD CONSTRAINT capstone_copyright_cert_unique UNIQUE (copyright_cert_id),
    ADD CONSTRAINT capstone_utilization_cert_unique UNIQUE (utilization_cert_id);

COMMIT;
