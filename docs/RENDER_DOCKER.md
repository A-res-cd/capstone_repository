# Render deployment with Tesseract OCR

The Dockerfile installs the Tesseract executable and English language data.
`pytesseract` is the Python wrapper and does not install the executable by itself.
PDF rendering uses the existing pypdfium2 dependency.

Push Dockerfile and .dockerignore to your GitHub repository. Create a Render Web
Service from that repository with these settings:

| Setting | Value |
| --- | --- |
| Language / runtime | Docker |
| Root directory | Blank when Dockerfile is at the repository root |
| Dockerfile path | `./Dockerfile` |
| Docker command override | Blank; use the Dockerfile's CMD |

Copy your existing Render environment variables to the Docker service, including
SECRET_KEY, all PG_* settings and the Supabase storage settings. If TESSERACT_CMD
is set in Render, use `/usr/bin/tesseract`; a Windows executable path will not work.
The Dockerfile supplies this Linux path by default. Keep secrets in Render's
environment settings, not in the image or Git repository.

Deploy, then upload an image-based COR PDF and check the extracted fields. The
image build checks `tesseract --version` so missing installation fails the build.
Keep the current service until the Docker service passes this check.

If Docker is installed locally, you can verify the image with:

```sh
docker build -t capre-ocr .
docker run --rm capre-ocr tesseract --list-langs
```

Reference: [Docker on Render](https://render.com/docs/docker).
