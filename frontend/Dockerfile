# # frontend/Dockerfile

# FROM node:16

# WORKDIR /app

# # Copy package.json and package-lock.json
# COPY package*.json ./

# # Install dependencies
# RUN npm install


# # ✅ ADD THIS LINE
# RUN npm install -g serve

# COPY . .
# RUN npm run build

# EXPOSE 3000

# # This command is now correct
# CMD [ "serve", "-s", "build", "-l", "3000" ]

FROM node:18-alpin
WORKDIR /app
COPY package*.json ./
RUN npm install
RUN npm install -g serve
COPY . .
RUN npm run build
EXPOSE 3000
CMD [ "serve", "-s", "build", "-l", "3000" ]