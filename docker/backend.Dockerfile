FROM python:3.14-slim

# Static ffmpeg build with full codec support (libx264, HEVC decode, AV1, etc.)
# Required for transcoding non-H.264 video (e.g. HEVC from TikTok) to browser-compatible H.264
COPY --from=mwader/static-ffmpeg:latest /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:latest /ffprobe /usr/local/bin/ffprobe

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

# JavaScript runtime for yt-dlp's signature / "n" challenge solver.
# Without it YouTube's web clients return storyboards only, which is what
# age-restricted videos are forced onto — cookies get past the age gate and
# then every real format is missing. Ordinary videos use the tv client and
# never needed this, so the gap only shows up once a login is in play.
RUN curl -fsSL -o /tmp/deno.zip \
      https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip \
    && unzip -q /tmp/deno.zip -d /usr/local/bin \
    && chmod 755 /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && deno --version | head -1

RUN useradd -m -u 1000 appuser

WORKDIR /app
RUN chown appuser /app

# Switch to non-root user before pip so packages land in ~/.local
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH

COPY --chown=appuser backend/requirements.txt ./
# Fail loudly and instantly if a wheel is missing for these, rather than falling
# back to an sdist that needs a C toolchain this image doesn't have.
ENV PIP_ONLY_BINARY=lxml,nh3,charset-normalizer
RUN pip install --user --no-cache-dir -r requirements.txt

COPY --chown=appuser backend/app ./app
COPY --chown=appuser docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

RUN mkdir -p /app/storage

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
