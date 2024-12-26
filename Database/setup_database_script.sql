DROP TABLE IF EXISTS editable_fields;
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS descriptions;

CREATE TABLE images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_extension VARCHAR(5) NOT NULL,
    user_id VARCHAR(18) NOT NULL,
    enumeration TINYINT NOT NULL,
    created_at DATETIME NOT NULL,
    filename VARCHAR(26) AS (CONCAT(user_id, "_", enumeration, ".", image_extension))
);

CREATE TABLE editable_fields (
    id INT AUTO_INCREMENT PRIMARY KEY,
    field_name VARCHAR(255) NOT NULL,
    type ENUM("text", "image") NOT NULL DEFAULT "text",
    up_bound SMALLINT NOT NULL,
    left_bound SMALLINT NOT NULL,
    down_bound SMALLINT NOT NULL,
    right_bound SMALLINT NOT NULL,
    image_id INT NOT NULL,
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
);

CREATE TABLE descriptions (
    field_name VARCHAR(255) NOT NULL PRIMARY KEY,
    description_text TEXT
);