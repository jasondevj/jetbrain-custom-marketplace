FROM nginx:1.27-alpine

# Python is used by the startup script to regenerate updatePlugins.xml from
# plugins.json and (in LOCAL_CACHE mode) pre-download plugin assets.
RUN apk add --no-cache python3

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/server_entrypoint.py /usr/local/bin/server_entrypoint.py
COPY docker/server-start.sh /usr/local/bin/server-start.sh
COPY public/index.html /etc/site/index.html

RUN chmod +x /usr/local/bin/server-start.sh

EXPOSE 80

ENTRYPOINT ["/usr/local/bin/server-start.sh"]
