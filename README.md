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

2. Install dependencies. It's recommended to use a virtual environment
   like [`virtualenv`](https://pypi.org/project/virtualenv/).

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

You can access the server at http://localhost:8080/. The default password for admin is `123456`. Please change it
immediately. Note that only moderate or higher role can register new users.

## Background Jobs

There are three background jobs in server.

* refresh_problem_all:
  This job is used to refresh problem data from scu and hdu online judge.
  It is scheduled to run every day at 13:13 and 22:13 in **UTC**.

* update_problem_all:
  This job is used to update problem data in database.
  It is scheduled to run every day at 13:29 and 22:29 in **UTC**.

* refresh_recent_contest:
  This job is used to refresh recent contest data from hdu online judge.
  It is scheduled to run every 5 minutes.

These scheduled jobs are not able to configure by config file yet. If you want to change the schedule, you can modify
the `AppConfig` in config.py.

