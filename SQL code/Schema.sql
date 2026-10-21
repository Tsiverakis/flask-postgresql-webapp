--Users
CREATE TABLE Users (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    surname VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    date_of_birth DATE,
    town VARCHAR(100),
    sex VARCHAR(20),
    password VARCHAR(255) NOT NULL
);

--Friends (Σχέση M:N μεταξύ Users)
CREATE TABLE Friends (
    user_id_1 INT REFERENCES Users(user_id) ON DELETE CASCADE,
    user_id_2 INT REFERENCES Users(user_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id_1, user_id_2),
    CHECK (user_id_1 != user_id_2) -- Αποτρέπει έναν χρήστη από το να είναι φίλος με τον εαυτό του
);

--Albums
CREATE TABLE Albums (
    album_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    user_id INT NOT NULL REFERENCES Users(user_id) ON DELETE CASCADE,
    creation_date DATE DEFAULT CURRENT_DATE
);

--Photos
CREATE TABLE Photos (
    photo_id SERIAL PRIMARY KEY,
    album_id INT NOT NULL REFERENCES Albums(album_id) ON DELETE CASCADE,
    caption TEXT,
    data BYTEA NOT NULL 
);

--Tags
CREATE TABLE Tags (
    tag_id SERIAL PRIMARY KEY,
    text VARCHAR(50) UNIQUE NOT NULL,
    -- Εξασφαλίζει μικρά γράμματα και απουσία κενών
    CHECK (text = LOWER(text) AND text NOT LIKE '% %') 
);

-- Συσχέτιση M:N μεταξύ Photos και Tags
CREATE TABLE Photo_Tags (
    photo_id INT REFERENCES Photos(photo_id) ON DELETE CASCADE,
    tag_id INT REFERENCES Tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (photo_id, tag_id)
);

--Comments
CREATE TABLE Comments (
    comment_id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    user_id INT REFERENCES Users(user_id) ON DELETE CASCADE,
    photo_id INT NOT NULL REFERENCES Photos(photo_id) ON DELETE CASCADE,
    post_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

--Likes (Σχέση M:N μεταξύ Users και Photos)
CREATE TABLE Likes (
    user_id INT REFERENCES Users(user_id) ON DELETE CASCADE,
    photo_id INT REFERENCES Photos(photo_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, photo_id)
);