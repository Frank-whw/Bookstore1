#!/bin/sh
export PATHONPATH=`pwd`
# coverage run --timid --branch --source fe,be --concurrency=thread -m pytest -v --ignore=fe/data
coverage run --timid --branch --source fe,be --omit="fe/bench/*,fe/test/test_enhanced_bench.py,be/app.py" --concurrency=thread -m pytest -v --ignore=fe/data --ignore=fe/bench --ignore=fe/test/test_enhanced_bench.py --ignore=be/app.py

coverage combine
coverage report
