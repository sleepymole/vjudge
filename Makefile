run:
	python run.py

fmt:
	black --extend-exclude=migrations .
