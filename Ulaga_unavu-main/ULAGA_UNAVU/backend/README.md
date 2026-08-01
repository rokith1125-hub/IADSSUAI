# ULAGA_UNAVU - Agriculture AI Platform Backend

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- MongoDB 6.0+
- Firebase Project
- Groq/OpenAI API Key

### Installation

1. **Clone and setup**
```bash
git clone <repository-url>
cd ULAGA_UNAVU/backend




#### **`backend/SECURITY.md`**
```markdown
# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities to: security@ulagau.com

## Security Practices

### 1. Authentication & Authorization
- Firebase Authentication for user management
- JWT token validation on all endpoints
- Role-based access control
- Session management with expiry

### 2. Data Protection
- No sensitive data stored in plain text
- MongoDB with authentication
- Environment variables for secrets
- Regular security updates

### 3. API Security
- CORS configured for specific origins
- Rate limiting on all endpoints
- Input validation and sanitization
- SQL/NoSQL injection prevention

### 4. Infrastructure
- Docker containers with minimal base images
- Regular dependency updates
- Security scanning in CI/CD
- HTTPS/TLS enforcement in production

### 5. Monitoring
- Logging of all authentication attempts
- Error tracking and alerting
- Regular security audits
- Penetration testing

## Security Updates

We regularly update dependencies and address security issues:

```bash
# Update Python packages
pip list --outdated
pip install -U package_name

# Check for security vulnerabilities
safety check

## **5. Setup Instructions:**

Create a setup script:

#### **`backend/setup.sh`**
```bash
#!/bin/bash

echo "Setting up ULAGA_UNAVU Backend..."

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "Creating directories..."
mkdir -p logs uploads temp_uploads datasets ai_models

# Copy environment file
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please edit .env file with your API keys and configuration"
fi

# Initialize MongoDB (if running locally)
echo "Checking MongoDB..."
if ! command -v mongod &> /dev/null; then
    echo "MongoDB not found. Please install MongoDB:"
    echo "Ubuntu: sudo apt install mongodb"
    echo "Mac: brew install mongodb-community"
    echo "Windows: Download from mongodb.com"
fi

# Create MongoDB data directory
mkdir -p data/db

echo ""
echo "Setup complete! Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Start MongoDB: mongod --dbpath ./data/db"
echo "3. Run backend: python app/main.py"
echo "4. Access API at: http://localhost:5000/api/health"