# vjudge

A virtual judge based on scu and hdu online judge.

## Prerequisite

* redis
* python (3.7+)
* database (sqlite3 or mysql)

## Quick start

1. Clone the repository.

```bash
git clone https://github.com/gozssky/vjudge.git
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Prepare a configuration file in working directory.

config-example.yml is a sample configuration file. You can copy it to config.yaml and modify it.

4. Initialize the database.

```bash
python init_db.py
```

5. Start the server.

```bash
python run.py
```

You can access the server at http://localhost:8080/.
