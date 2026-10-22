from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os
import base64


app = Flask(__name__)

# Flask encrypts the session cookie after logging in
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_fallback_dev_key')

# --- DATABASE SETUP ---


def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="k29photo",
        user="postgres",
        password="Enter your database password here"
    )
    return conn
# ----------------------


@app.route("/")
@app.route("/home")
def home():
    # If the user is NOT logged in, just render the home page with no user data
    if 'user_id' not in session:
        return render_template("home.html")

    # If the user IS logged in, fetch their specific data
    current_user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()

    search_term = request.args.get("friend_search", "").strip()

    # Get all the friends of the user
    friends_query = """
        SELECT name, surname 
        FROM Users 
        WHERE user_id IN (
            SELECT user_id_2 FROM Friends WHERE user_id_1 = %s
            UNION
            SELECT user_id_1 FROM Friends WHERE user_id_2 = %s
        )
    """
    query_parameters = [current_user_id, current_user_id]

    # If the user searches for a friend add a filter
    if search_term:
        friends_query += " AND (name ILIKE %s OR surname ILIKE %s)"
        like_term = f"%{search_term}%"
        query_parameters.extend([like_term, like_term])

    cur.execute(friends_query, tuple(query_parameters))
    friends_data = cur.fetchall()

    # get the top ten contributors
    top_users_query = """
        SELECT 
            u.name, 
            u.surname,
            (
                SELECT COUNT(*)
                FROM Albums a
                JOIN Photos p ON a.album_id = p.album_id
                WHERE a.user_id = u.user_id
            ) 
            + 
            (
                SELECT COUNT(*)
                FROM Comments c
                JOIN Photos p ON c.photo_id = p.photo_id
                JOIN Albums a ON p.album_id = a.album_id
                WHERE c.user_id = u.user_id AND a.user_id != u.user_id
            ) AS total_score
        FROM Users u
        ORDER BY total_score DESC
        LIMIT 10;
    """
    cur.execute(top_users_query)
    top_users_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("home.html",
                           current_user_name=session['name'],
                           friends=friends_data,
                           top_users=top_users_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    # If the user clicks the "Log in" button, show them the login page
    if request.method == "GET":
        return render_template("login.html")

    # If they are submitting the form:
    email = request.form.get("email")
    password = request.form.get("password")

    conn = get_db_connection()
    cur = conn.cursor()

    # Get user info from db
    cur.execute(
        "SELECT user_id, name, password FROM Users WHERE email = %s", (email,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    # If the user was found
    if user:
        db_user_id = user[0]
        db_name = user[1]
        db_hashed_password = user[2]

        # check for correct password
        if check_password_hash(db_hashed_password, password):
            session['user_id'] = db_user_id
            session['name'] = db_name
            return redirect(url_for('home'))
        else:
            return "Incorrect password. Please try again."
    else:
        return "Email not found. Please sign up."


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route("/Signup", methods=["GET", "POST"])
def sign_up():
    if request.method == "POST":
        name = request.form.get("name")
        surname = request.form.get("surname")
        email = request.form.get("email")
        dob = request.form.get("date_of_birth")
        town = request.form.get("town")
        sex = request.form.get("sex")
        password = request.form.get("password")

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute('SELECT * FROM Users WHERE email = %s', (email,))
        existing_user = cur.fetchone()

        # Check if a user with the same credentials exists
        if existing_user:
            cur.close()
            conn.close()
            return "Error: An account with that email already exists! Please try logging in."

        # Generate a hashed password for security
        hashed_password = generate_password_hash(password)

        try:
            # Add the new user into the db
            cur.execute(
                '''INSERT INTO Users (name, surname, email, date_of_birth, town, sex, password) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (name, surname, email, dob, town, sex, hashed_password)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            return f"A database error occurred: {e}"
        finally:
            cur.close()
            conn.close()

        return f"Registration successful for {name} {surname}! Data is saved in PostgreSQL."

    return render_template("signup.html")


@app.route("/home/add_friend", methods=["GET", "POST"])
def add_friend():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']

    if request.method == "POST":
        friend_id_str = request.form.get("friend_id")

        if not friend_id_str or not friend_id_str.isdigit():
            return "Παρακαλώ εισάγετε ένα έγκυρο ID (ακέραιο αριθμό)."

        friend_id = int(friend_id_str)

        if friend_id == current_user_id:
            return "Δεν μπορείτε να προσθέσετε τον εαυτό σας στους φίλους σας."

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # Get the user_id of the person that is being added(checking it exists)
            cur.execute(
                "SELECT user_id FROM Users WHERE user_id = %s", (friend_id,))
            user_exists = cur.fetchone()

            if not user_exists:
                return f"Δεν βρέθηκε χρήστης με ID {friend_id}."

            # Checking friends table if the person is already a friend of the user
            cur.execute("""
                SELECT * FROM Friends 
                WHERE (user_id_1 = %s AND user_id_2 = %s) 
                   OR (user_id_1 = %s AND user_id_2 = %s)
            """, (current_user_id, friend_id, friend_id, current_user_id))

            already_friends = cur.fetchone()

            if already_friends:
                return "Είστε ήδη φίλοι με αυτόν τον χρήστη!"

            # Adding the person as a friend
            cur.execute(
                "INSERT INTO Friends (user_id_1, user_id_2) VALUES (%s, %s)",
                (current_user_id, friend_id)
            )
            conn.commit()
            return f"Τέλεια! O χρήστης με ID {friend_id} προστέθηκε στους φίλους σας."

        except Exception as e:
            conn.rollback()
            return f"Προέκυψε σφάλμα: {e}"
        finally:
            cur.close()
            conn.close()

    # Get the name or the surname of a user
    search_query = request.args.get("search_user", "").strip()
    search_results = []

    if search_query:
        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # Get matching users (ingore caps)
            search_sql = """
                SELECT user_id, name, surname 
                FROM Users 
                WHERE (name ILIKE %s OR surname ILIKE %s)
                  AND user_id != %s  -- Δεν θέλουμε να του βγάλει τον εαυτό του στα αποτελέσματα
            """
            like_term = f"%{search_query}%"

            cur.execute(search_sql, (like_term, like_term, current_user_id))
            search_results = cur.fetchall()

        except Exception as e:
            print(f"Σφάλμα κατά την αναζήτηση χρήστη: {e}")
        finally:
            cur.close()
            conn.close()

    return render_template("add_friend.html",
                           search_results=search_results,
                           search_query=search_query)


@app.route("/home/view_photos", methods=["GET", "POST"])
def view_photos():
    view_mode = request.args.get("view", "all")
    conn = get_db_connection()
    cur = conn.cursor()

    if view_mode == "mine":
        if 'user_id' not in session:
            return redirect(url_for('login'))

        current_user_id = session['user_id']
        # Get photos and commnents for the user`s posts
        query = """
            SELECT p.photo_id, p.caption, p.data, c.text, u.name, a.user_id
            FROM Photos p
            JOIN Albums a ON p.album_id = a.album_id
            LEFT JOIN Comments c ON p.photo_id = c.photo_id
            LEFT JOIN Users u ON c.user_id = u.user_id
            WHERE a.user_id = %s
            ORDER BY p.photo_id
        """
        cur.execute(query, (current_user_id,))
    else:
        # Get all photos and comments
        query = """
            SELECT p.photo_id, p.caption, p.data, c.text, u.name, a.user_id
            FROM Photos p
            JOIN Albums a ON p.album_id = a.album_id
            LEFT JOIN Comments c ON p.photo_id = c.photo_id
            LEFT JOIN Users u ON c.user_id = u.user_id
            ORDER BY p.photo_id
        """
        cur.execute(query)

    all_photos = cur.fetchall()

    # Get likes and users that liked
    likes_query = """
        SELECT l.photo_id, u.name, u.surname 
        FROM Likes l
        JOIN Users u ON l.user_id = u.user_id
    """
    cur.execute(likes_query)
    all_likes = cur.fetchall()

    cur.close()
    conn.close()

    photos_dict = {}

    # Create the dictionary with photos and comments
    for row in all_photos:
        photo_id = row[0]
        caption = row[1]
        binary_data = row[2]
        comment_text = row[3]
        commenter_name = row[4]
        owner_id = row[5]

        if photo_id not in photos_dict:
            encoded_image = base64.b64encode(binary_data).decode(
                'utf-8') if binary_data else ""

            photos_dict[photo_id] = {
                'photo_id': photo_id,
                'owner_id': owner_id,
                'caption': caption,
                'image': encoded_image,
                'comments': [],
                'likers': []
            }

        if comment_text:
            photos_dict[photo_id]['comments'].append({
                'text': comment_text,
                'author': commenter_name or "Guest"
            })

    # Add likes to the corresponding photots
    for row in all_likes:
        like_photo_id = row[0]
        # Connect name and surname
        liker_full_name = f"{row[1]} {row[2]}"

        # If photo exists add liker
        if like_photo_id in photos_dict:
            photos_dict[like_photo_id]['likers'].append(liker_full_name)

    photos_for_html = list(photos_dict.values())

    return render_template("photos.html", photos=photos_for_html, current_view=view_mode)


@app.route("/home/add_like", methods=["POST"])
def add_like():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for('login'))

    photo_id = request.form.get("photo_id")
    conn = get_db_connection()
    cur = conn.cursor()

    # Adds a like into the talbe on the corresponding photo(prevents problems with double clicking like button)
    query = """
            INSERT INTO Likes (User_id, Photo_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING; 
    """

    try:
        cur.execute(query, (user_id, photo_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Σφάλμα κατά την αποθήκευση του Like: {e}"
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('view_photos'))


@app.route("/home/add_comment", methods=["POST"])
def add_comment():
    photo_id = request.form.get("photo_id")
    owner_id = request.form.get("owner_id")
    text = request.form.get("comment_text")

    current_user_id = session.get('user_id')

    # Current user cant comment on his/her photos
    if current_user_id and str(current_user_id) == str(owner_id):
        return "Δεν μπορείτε να αφήσετε σχόλιο στη δική σας φωτογραφία!"

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Adds the comment into the table with the current date
        cur.execute("""
            INSERT INTO Comments (text, user_id, photo_id, post_date) 
            VALUES (%s, %s, %s, CURRENT_DATE)
        """, (text, current_user_id, photo_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Σφάλμα κατά την αποθήκευση του σχολίου: {e}"
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('view_photos'))


@app.route("/home/view_albums", methods=["GET"])
def view_albums():
    # get 'view' parameter from url(default = 'all')
    view_mode = request.args.get("view", "all")

    conn = get_db_connection()
    cur = conn.cursor()

    if view_mode == "mine":
        # If the user is not logged in he cant view his/her albums
        if 'user_id' not in session:
            return redirect(url_for('login'))

        current_user_id = session['user_id']
        # Get the users albums from the db
        query = """
            SELECT album_id, name, creation_date
            FROM albums
            WHERE user_id = %s
        """
        cur.execute(query, (current_user_id,))
    else:
        # Get all the albums from the db
        query = """
            SELECT album_id, name, creation_date
            FROM albums
        """
        cur.execute(query)

    all_albums = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("view_albums.html", albums=all_albums, current_view=view_mode)


@app.route("/home/albums/<int:album_id>/photos")
def album_photos(album_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Get the album name to display it at the title
    cur.execute("SELECT name FROM Albums WHERE album_id = %s", (album_id,))
    album_record = cur.fetchone()

    # If the album id does not exist stop
    if not album_record:
        cur.close()
        conn.close()
        return "Το album δεν βρέθηκε.", 404

    album_name = album_record[0]

    # get all the photos with the specific album id
    query = """
        SELECT photo_id, caption, data 
        FROM Photos 
        WHERE album_id = %s
    """
    cur.execute(query, (album_id,))
    photos_data = cur.fetchall()

    cur.close()
    conn.close()

    # convert binary into Base64
    photos_for_html = []
    for photo in photos_data:
        photo_id = photo[0]
        caption = photo[1]
        binary_data = photo[2]

        if binary_data:
            encoded_image = base64.b64encode(binary_data).decode('utf-8')
        else:
            encoded_image = ""

        photos_for_html.append((photo_id, caption, encoded_image))

    return render_template("album_photos.html", photos=photos_for_html, album_name=album_name)


@app.route("/home/create_album", methods=["GET", "POST"])
def create_album():

    if request.method == "GET":
        return render_template("create_album.html")

    name = request.form.get("name")
    user_id = session['user_id']

    if not name or not user_id:
        return "Παρακαλώ συμπληρώστε το όνομα του άλμπουμ και το ID χρήστη."

    try:
        user_id = int(user_id)
    except ValueError:
        return "Το ID του χρήστη πρέπει να είναι αριθμός."

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check if the user exists
        cur.execute("SELECT user_id FROM Users WHERE user_id = %s", (user_id,))
        user_exists = cur.fetchone()

        if not user_exists:
            return f"Σφάλμα: Δεν βρέθηκε χρήστης με ID {user_id}."

        # Add the album into albums table
        cur.execute(
            "INSERT INTO Albums (name, user_id) VALUES (%s, %s)",
            (name, user_id)
        )

        conn.commit()
        return f"Τέλεια! To άλμπουμ '{name}' δημιουργήθηκε με επιτυχία."

    except Exception as e:
        # In case of failure we rollback the db to stop the transaction
        conn.rollback()
        return f"Προέκυψε ένα σφάλμα κατά την αποθήκευση: {e}"
    finally:
        cur.close()
        conn.close()

    return render_template("create_album.html")


@app.route("/home/create_photo", methods=["GET", "POST"])
def create_photo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()

    # GET: Load page and display albums
    if request.method == "GET":
        # Get only the users albums
        cur.execute(
            "SELECT album_id, name FROM Albums WHERE user_id = %s", (current_user_id,))
        user_albums = cur.fetchall()

        cur.close()
        conn.close()

        # If the user does no t have an album he can not post a photo
        if not user_albums:
            return "Πρέπει να δημιουργήσετε πρώτα ένα άλμπουμ (από το create_album) για να ανεβάσετε φωτογραφία!"

        return render_template("create_photo.html", albums=user_albums)

  # POST: Save photo in database
    if request.method == "POST":

        album_id = request.form.get("album_id")
        caption = request.form.get("caption")

        tags_string = request.form.get("tags", "")

        photo_file = request.files.get("photo_data")

        # Check if a file was given and an album was chosen
        if not album_id or not photo_file or photo_file.filename == '':
            return "Παρακαλώ επιλέξτε άλμπουμ και ανεβάστε ένα έγκυρο αρχείο φωτογραφίας."

        photo_binary = photo_file.read()

        try:
            # Add the photo into photos table and return its id
            cur.execute(
                "INSERT INTO Photos (album_id, caption, data) VALUES (%s, %s, %s) RETURNING photo_id",
                (album_id, caption, psycopg2.Binary(photo_binary))
            )
            new_photo_id = cur.fetchone()[0]

            # Check if the user added a tag
            if tags_string.strip():

                tags_list = tags_string.lower().split()

                # Make a list of the albums and remove any dublicates
                tags_list = list(set(tags_list))

                for tag_word in tags_list:
                    # Check if the tag already exists
                    cur.execute(
                        "SELECT tag_id FROM Tags WHERE text = %s", (tag_word,))
                    tag_record = cur.fetchone()

                    if tag_record:
                        tag_id = tag_record[0]
                    else:
                        # If the tag does not exist insert it into table tags and get back its id
                        cur.execute(
                            "INSERT INTO Tags (text) VALUES (%s) RETURNING tag_id",
                            (tag_word,)
                        )
                        tag_id = cur.fetchone()[0]

                    # Connect the photo with the tag via the junction table photo_tags by adding the photo id and the tag id
                    cur.execute(
                        "INSERT INTO Photo_Tags (photo_id, tag_id) VALUES (%s, %s)",
                        (new_photo_id, tag_id)
                    )

            conn.commit()
            return "Η φωτογραφία μεταφορτώθηκε με επιτυχία στο άλμπουμ!"

        except Exception as e:
            conn.rollback()
            return f"Σφάλμα κατά την αποθήκευση: {e}"
        finally:
            cur.close()
            conn.close()


@app.route("/home/delete_photo/<int:photo_id>", methods=["POST"])
def delete_photo(photo_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check if the photo belongs to an album of the current user
        cur.execute("""
            SELECT a.user_id 
            FROM Photos p
            JOIN Albums a ON p.album_id = a.album_id
            WHERE p.photo_id = %s
        """, (photo_id,))
        result = cur.fetchone()

        if not result:
            return "Η φωτογραφία δεν βρέθηκε."

        if result[0] != current_user_id:
            return "Δεν έχετε δικαίωμα να διαγράψετε αυτή τη φωτογραφία."

        cur.execute("DELETE FROM Photos WHERE photo_id = %s", (photo_id,))
        conn.commit()

    except Exception as e:
        conn.rollback()
        return f"Σφάλμα κατά τη διαγραφή της φωτογραφίας: {e}"
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('view_photos', view='mine'))


@app.route("/home/delete_album/<int:album_id>", methods=["POST"])
def delete_album(album_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check if the album belongs to the current user
        cur.execute(
            "SELECT user_id FROM Albums WHERE album_id = %s", (album_id,))
        result = cur.fetchone()

        if not result:
            return "Το άλμπουμ δεν βρέθηκε."

        if result[0] != current_user_id:
            return "Δεν έχετε δικαίωμα να διαγράψετε αυτό το άλμπουμ."

        cur.execute("DELETE FROM Albums WHERE album_id = %s", (album_id,))
        conn.commit()

    except Exception as e:
        conn.rollback()
        return f"Σφάλμα κατά τη διαγραφή του άλμπουμ: {e}"
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('view_albums', view='mine'))


@app.route("/home/tags", methods=["GET"])
def tags():
    search_query = request.args.get("query", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    # Get all the tags
    query_all_tags = """
        SELECT text
        FROM tags
    """
    cur.execute(query_all_tags)
    all_tags = cur.fetchall()

    # Get the top 5 tags
    query_popular = """
        SELECT t.text, COUNT(pt.photo_id) AS photo_count
        FROM tags t
        JOIN photo_tags pt ON t.tag_id = pt.tag_id
        GROUP BY t.tag_id, t.text
        ORDER BY photo_count DESC
        LIMIT 5
    """
    cur.execute(query_popular)
    popular_tags = cur.fetchall()

    # If the user did a search get all the photos
    encoded_photos = []

    if search_query:
        tag_list = list(set(search_query.lower().split()))
        num_tags = len(tag_list)
        tags_tuple = tuple(tag_list)

        # Get the photos binary data
        search_sql = """
            SELECT p.data
            FROM photos p
            JOIN photo_tags pt ON p.photo_id = pt.photo_id
            JOIN tags t ON pt.tag_id = t.tag_id
            WHERE t.text IN %s
            GROUP BY p.photo_id, p.data
            HAVING COUNT(DISTINCT t.tag_id) = %s
        """
        cur.execute(search_sql, (tags_tuple, num_tags))
        found_photos = cur.fetchall()

        # Convert photo data from binary to base64
        for p in found_photos:
            if p[0]:
                base64_str = base64.b64encode(p[0]).decode('utf-8')
                encoded_photos.append(base64_str)

    cur.close()
    conn.close()

    return render_template("tags.html",
                           all_tags=all_tags,
                           popular_tags=popular_tags,
                           search_photos=encoded_photos,
                           query=search_query)


@app.route("/home/tags/<tag_name>")
def tag(tag_name):
    view = request.args.get("view", "all")

    conn = get_db_connection()
    cur = conn.cursor()

    if view == "mine":
        # Make sure the user is logged in
        current_user_id = session.get('user_id')

        query = """
            SELECT p.data
            FROM photos p
            JOIN albums a ON a.album_id = p.album_id
            JOIN photo_tags pt ON pt.photo_id = p.photo_id
            JOIN tags t ON t.tag_id = pt.tag_id
            WHERE t.text = %s AND a.user_id = %s           
        """
        cur.execute(query, (tag_name, current_user_id))

    elif view == "all":
        query = """
            SELECT p.data
            FROM photos p 
            JOIN photo_tags pt ON pt.photo_id = p.photo_id
            JOIN tags t ON t.tag_id = pt.tag_id
            WHERE t.text = %s                               
        """
        cur.execute(query, (tag_name,))

    photos = cur.fetchall()

    cur.close()
    conn.close()

    encoded_photos = []

    for p in photos:
        if p[0]:
            base64_str = base64.b64encode(p[0]).decode('utf-8')
            encoded_photos.append(base64_str)

    return render_template("tag_photos.html", tag_name=tag_name, photos=encoded_photos, view=view)


@app.route("/home/search_comments", methods=["GET"])
def search_comments():
    # Get the search query
    search_query = request.args.get("query", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    results = []

    if search_query:
        # Search for users with the exact same text and count their comments
        sql_query = """
            SELECT u.name, u.surname, COUNT(c.comment_id) AS match_count
            FROM Users u
            JOIN Comments c ON u.user_id = c.user_id
            WHERE c.text = %s
            GROUP BY u.user_id, u.name, u.surname
            ORDER BY match_count DESC
        """

        try:
            cur.execute(sql_query, (search_query,))
            results = cur.fetchall()
        except Exception as e:
            conn.rollback()
            return f"Προέκυψε σφάλμα κατά την αναζήτηση: {e}"
        finally:
            cur.close()
            conn.close()
    else:
        cur.close()
        conn.close()

    return render_template("search_comments.html", results=results, query=search_query)


if __name__ == '__main__':
    app.run(host="localhost", port=5000, debug=True)
