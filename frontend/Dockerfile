FROM nginx:alpine

# Copy static frontend placeholder files
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
