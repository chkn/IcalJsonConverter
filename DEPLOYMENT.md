# Deployment Guide for iCal to JSON Converter API

This guide provides instructions for deploying the iCal to JSON Converter API to various cloud environments.

## Prerequisites

- Docker installed on your local machine
- Access to your cloud provider's CLI or web console
- Git repository with your application code

## Deployment Options

### Option 1: Deploy to AWS Elastic Container Service (ECS)

1. **Create an ECR Repository**

   ```bash
   aws ecr create-repository --repository-name ical-to-json-api
   ```

2. **Authenticate with ECR**

   ```bash
   aws ecr get-login-password | docker login --username AWS --password-stdin <your-aws-account-id>.dkr.ecr.<region>.amazonaws.com
   ```

3. **Build and Push the Docker Image**

   ```bash
   docker build -t ical-to-json-api .
   docker tag ical-to-json-api:latest <your-aws-account-id>.dkr.ecr.<region>.amazonaws.com/ical-to-json-api:latest
   docker push <your-aws-account-id>.dkr.ecr.<region>.amazonaws.com/ical-to-json-api:latest
   ```

4. **Create an ECS Cluster, Task Definition, and Service**

   Use the AWS ECS console or CLI to create these resources. Make sure to:
   - Expose port 5000
   - Set environment variables (e.g., SESSION_SECRET)
   - Configure appropriate CPU and memory limits

### Option 2: Deploy to Google Cloud Run

1. **Build and Push to Google Container Registry**

   ```bash
   gcloud auth configure-docker
   docker build -t gcr.io/<your-gcp-project>/ical-to-json-api .
   docker push gcr.io/<your-gcp-project>/ical-to-json-api
   ```

2. **Deploy to Cloud Run**

   ```bash
   gcloud run deploy ical-to-json-api \
     --image gcr.io/<your-gcp-project>/ical-to-json-api \
     --platform managed \
     --port 5000 \
     --set-env-vars="SESSION_SECRET=your-secret-value" \
     --allow-unauthenticated
   ```

### Option 3: Deploy to Azure Container Instances

1. **Create an Azure Container Registry**

   ```bash
   az acr create --resource-group myResourceGroup --name myRegistry --sku Basic
   ```

2. **Build and Push to Azure Container Registry**

   ```bash
   az acr login --name myRegistry
   docker build -t myregistry.azurecr.io/ical-to-json-api:latest .
   docker push myregistry.azurecr.io/ical-to-json-api:latest
   ```

3. **Deploy to Azure Container Instances**

   ```bash
   az container create \
     --resource-group myResourceGroup \
     --name ical-to-json-api \
     --image myregistry.azurecr.io/ical-to-json-api:latest \
     --dns-name-label ical-to-json-api \
     --ports 5000 \
     --environment-variables SESSION_SECRET=your-secret-value
   ```

### Option 4: Deploy to Digital Ocean App Platform

1. **Create a new app in Digital Ocean App Platform**
   
   - Connect your repository
   - Choose the "Docker" type
   - Configure the app to expose port 5000
   - Set environment variables

2. **Deploy the app**

   Follow the DigitalOcean interface to deploy your app.

## Setting Up Custom Domain

For production deployments, you'll want to set up a custom domain:

1. Register a domain or use an existing one
2. Configure DNS records to point to your deployment
3. Set up SSL certificate (most cloud providers offer automated Let's Encrypt integration)

## Environment Variables

The following environment variables should be set for production deployments:

- `SESSION_SECRET`: A secure random string for session encryption
- `PORT`: (Optional) Override the default port (5000)

## Health Checks and Monitoring

The Docker container includes a health check at `/` that returns a 200 status when the service is healthy.

For production deployments, consider setting up:

1. **Uptime monitoring** with services like Pingdom, UptimeRobot, or your cloud provider's monitoring
2. **Log management** with CloudWatch Logs, Google Cloud Logging, or a third-party solution
3. **Performance monitoring** with services like New Relic, Datadog, or your cloud provider's APM solution

## Scaling Considerations

The iCal to JSON Converter API is designed to be horizontally scalable:

- It is stateless (no session state is stored on the server)
- It can run behind a load balancer
- Multiple instances can be deployed for high availability