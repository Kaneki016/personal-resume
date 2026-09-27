BEGIN;
ALTER TABLE portfolio.projects ADD COLUMN IF NOT EXISTS screenshots TEXT NOT NULL DEFAULT '[]';
-- Match the original entries by title. Preserve any existing gallery or custom cover.
UPDATE portfolio.projects SET screenshots='["/assets/images/project/project-5.jpg","/assets/images/project/project-6.jpg","/assets/images/project/project-7.jpg","/assets/images/project/project-8.jpg"]',
  image=CASE WHEN image='' THEN '/assets/images/project/project-5.jpg' ELSE image END
WHERE title='IMAX Financial client portal' AND screenshots='[]';
UPDATE portfolio.projects SET screenshots='["/assets/images/project/project-1.jpg","/assets/images/project/project-2.jpg"]'
WHERE title='Video Translator' AND screenshots='[]';
UPDATE portfolio.projects SET screenshots='["/assets/images/project/project-3.jpg","/assets/images/project/project-4.jpg"]'
WHERE title='Cards Against Redditors' AND screenshots='[]';
COMMIT;
