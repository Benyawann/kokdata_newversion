CREATE TABLE station_data (
    id SERIAL PRIMARY KEY,
    river VARCHAR(100),
    station VARCHAR(100),
    location VARCHAR(200),
    tambon VARCHAR(100),
    amphoe VARCHAR(100),
    province VARCHAR(100)
);

CREATE TABLE water_data (
    id SERIAL PRIMARY KEY,
    station VARCHAR(100),
    parameter VARCHAR(100),
    location VARCHAR(200),
    check_number VARCHAR(50),
    value VARCHAR(100),
    numeric_value NUMERIC,
    unit VARCHAR(50)
);

CREATE TABLE soil_data (
    id SERIAL PRIMARY KEY,
    station VARCHAR(100),
    parameter VARCHAR(100),
    location VARCHAR(200),
    check_number VARCHAR(50),
    value VARCHAR(100),
    numeric_value NUMERIC
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100),
    password VARCHAR(100)
);