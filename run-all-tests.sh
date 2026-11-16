set -e
docker build -t citadel-test:latest --target test .
docker run --rm -ti citadel-test:latest
