# mysql> GRANT SELECT, INSERT, UPDATE, DELETE ON library.books, library.authors TO 'admin'@'localhost';

# chmod +x exportsqldb.sh
sudo mysqldump library  > lib.sql;