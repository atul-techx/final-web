CREATE TABLE IF NOT EXISTS notes (
  id           VARCHAR(32)   NOT NULL PRIMARY KEY,
  title        VARCHAR(255)  NOT NULL,
  subject      VARCHAR(100)  NOT NULL DEFAULT 'Other',
  description  TEXT,
  uploader     VARCHAR(100)  NOT NULL DEFAULT 'Anonymous',
  filename     VARCHAR(255)  NOT NULL,
  original_name VARCHAR(255) NOT NULL,
  ext          VARCHAR(20)   NOT NULL,
  size         VARCHAR(30)   NOT NULL,
  downloads    INT           NOT NULL DEFAULT 0,
  status       VARCHAR(20)   NOT NULL DEFAULT 'pending',
  uploaded_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_subject ON notes (subject);
CREATE INDEX IF NOT EXISTS idx_uploader ON notes (uploader);
CREATE INDEX IF NOT EXISTS idx_uploaded ON notes (uploaded_at);

CREATE TABLE IF NOT EXISTS settings (
  `key`   VARCHAR(100) NOT NULL PRIMARY KEY,
  `value` TEXT
);

INSERT INTO settings (`key`, `value`) VALUES
  ('site_title',      'NoteShare'),
  ('site_tagline',    'Collaborative Learning Platform'),
  ('hero_heading',    'Knowledge Grows When Shared'),
  ('hero_sub',        'Upload, discover, and download lecture notes effortlessly.'),
  ('footer_text',     'Made with ♥ by Utkarsh, Sachin, Rohit & Naitik'),
  ('primary_color',   '#e0217a'),
  ('allow_uploads',   'true'),
  ('show_downloads',  'true'),
  ('admin_password',  'admin'),
  ('contact_name',    'Utkarsh Agarwal'),
  ('contact_role',    'Creator & Developer — NoteShare'),
  ('contact_email',   'agarwalutkarsh1948@gmail.com'),
  ('contact_phone',   '+91 7818026130'),
  ('contact_linkedin','https://www.linkedin.com/in/utkarsh-agarwal-a436a2383/')
ON CONFLICT(`key`) DO NOTHING;
