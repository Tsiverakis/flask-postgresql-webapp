-- Συνάρτηση που ελέγχει τον ιδιοκτήτη της φωτογραφίας
CREATE OR REPLACE FUNCTION check_comment_owner()
RETURNS TRIGGER AS $$
DECLARE
    photo_owner_id INT;
BEGIN
    -- Βρίσκει τον ιδιοκτήτη (user_id) του άλμπουμ στο οποίο ανήκει η φωτογραφία
    SELECT a.user_id INTO photo_owner_id
    FROM Photos p
    JOIN Albums a ON p.album_id = a.album_id
    WHERE p.photo_id = NEW.photo_id;

    -- Ελέγχουμε αν αυτός που κάνει το σχόλιο (NEW.user_id) είναι ο ίδιος με τον ιδιοκτήτη
    IF NEW.user_id = photo_owner_id THEN
        RAISE EXCEPTION 'Απαγορεύεται να σχολιάσετε τη δική σας φωτογραφία.';
    END IF;

    -- Αν όλα είναι καλά, επιτρέπουμε την εισαγωγή
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Δημιουργία του Trigger που καλεί τη συνάρτηση πριν από κάθε INSERT στον πίνακα Comments
CREATE TRIGGER trg_prevent_own_photo_comment
BEFORE INSERT ON Comments
FOR EACH ROW
EXECUTE FUNCTION check_comment_owner();