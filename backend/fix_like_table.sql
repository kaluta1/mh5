-- Corriger la clé étrangère de la table like
ALTER TABLE "like" DROP CONSTRAINT IF EXISTS like_user_id_fkey;
ALTER TABLE "like" ADD CONSTRAINT like_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);

