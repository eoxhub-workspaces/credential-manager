# build is docker-compose build
all:
	docker-compose run my-credentials bash -c "pytest && flake8 && mypy ."

test:
	docker-compose run my-credentials pytest -s

test-watch:
	docker-compose run my-credentials ptw

lint:
	docker-compose run my-credentials bash -c "flake8 && mypy ."

lint-watch:
	docker-compose run my-credentials bash -c "watch -n1  bash -c \"flake8 && mypy .\""

upgrade-packages:
	docker-compose run --user 0 my-credentials bash -c "python3 -m pip install pip-upgrader && pip-upgrade --skip-package-installation"

bash:
	docker-compose run --user `id -u` my-credentials bash

build:
	docker-compose build
