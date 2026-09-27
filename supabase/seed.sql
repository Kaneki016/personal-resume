BEGIN;
SET LOCAL search_path TO portfolio;
DO $$ BEGIN IF EXISTS (SELECT 1 FROM projects) THEN RAISE EXCEPTION 'Projects already exist; seed cancelled.'; END IF; END $$;
INSERT INTO projects (title,category,summary,details,tags,url,image,published,position) VALUES ('IMAX Financial client portal','Client work','A WordPress website redesigned around useful, interactive financial tools.','Redesigned the company’s static WordPress website with WhatsApp contact integration, a Money Personality Quiz, and a Retirement Calculator.','WordPress, PHP, CSS','','',1,1);
INSERT INTO projects (title,category,summary,details,tags,url,image,published,position) VALUES ('Video Translator','Personal project','A web application exploring video translation across languages.','A hobby project built to explore a video translation workflow, from selecting a video to reviewing its translated output.','Video processing, Translation','','/assets/images/project/project-1.jpg',1,2);
INSERT INTO projects (title,category,summary,details,tags,url,image,published,position) VALUES ('Cards Against Redditors','Personal project','A real-time multiplayer game where Reddit comments become debate cards.','Players use Reddit comments in a multiplayer debate game. A personal project exploring interactive gameplay and real-time experiences.','Real-time multiplayer, Game development','','/assets/images/project/project-3.jpg',1,3);
UPDATE portfolio.projects SET screenshots='["/assets/images/project/project-5.jpg","/assets/images/project/project-6.jpg","/assets/images/project/project-7.jpg","/assets/images/project/project-8.jpg"]',
  image=CASE WHEN image='' THEN '/assets/images/project/project-5.jpg' ELSE image END
WHERE title='IMAX Financial client portal' AND screenshots='[]';
UPDATE portfolio.projects SET screenshots='["/assets/images/project/project-1.jpg","/assets/images/project/project-2.jpg"]'
WHERE title='Video Translator' AND screenshots='[]';
UPDATE portfolio.projects SET screenshots='["/assets/images/project/project-3.jpg","/assets/images/project/project-4.jpg"]'
WHERE title='Cards Against Redditors' AND screenshots='[]';
COMMIT;
