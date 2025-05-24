#!/bin/bash
gunicorn -b 0.0.0.0:$PORT main:app
chmod +x start.sh
