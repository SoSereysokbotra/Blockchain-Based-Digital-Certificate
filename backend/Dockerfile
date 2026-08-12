FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies.
#
# WeasyPrint needs Pango, Cairo, GDK-Pixbuf and HarfBuzz plus fontconfig and at
# least one real font family — without fonts installed the PDF renders but every
# glyph comes out as a blank box, which silently breaks the Phase 4 text
# extraction test. libzbar0 is required by pyzbar, used to decode the QR code
# back out of the generated PDF in that same test.
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        libpq-dev \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libharfbuzz0b \
        libffi-dev \
        shared-mime-info \
        fontconfig \
        fonts-dejavu-core \
        fonts-liberation \
        libzbar0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
