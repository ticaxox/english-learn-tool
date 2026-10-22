FROM nginx:1.27-alpine

RUN addgroup -S -g 10001 app \
    && adduser -S -D -H -u 10001 -G app app \
    && rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp /var/cache/nginx/fastcgi_temp /var/cache/nginx/uwsgi_temp /var/cache/nginx/scgi_temp \
    && chown -R app:app /var/cache/nginx /tmp

COPY deploy/reverse-proxy/nginx.conf /etc/nginx/nginx.conf

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
