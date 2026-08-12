# Blockchain-Based Digital Certificate Issuing Platform (BCIP)

This project provides a complete solution for issuing, managing, and verifying digital certificates backed by the Polygon Amoy blockchain. 
The system features an API backend in Django, and a suite of smart contracts.

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Requirements](#requirements)
- [Setup via Docker (Recommended)](#setup-via-docker-recommended)
- [Deploying the Smart Contract](#deploying-the-smart-contract)
- [Configuration (.env)](#configuration-env)
- [Running the Tests](#running-the-tests)

## Architecture Overview

The platform uses:
- **Django & Django REST Framework** for the core backend API.
- **PostgreSQL** as the primary relational database (and also for caching and rate limiting).
- **Hardhat** for smart contract development and testing.
- **WeasyPrint** for PDF generation.
- **django-q2** for background task processing (email notifications and blockchain transactions).

## Requirements

- **Docker** and **Docker Compose**
- **Node.js** (for deploying the smart contract manually, though testing is containerized).

## Setup via Docker (Recommended)

To quickly spin up the environment from scratch, you only need Docker.

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```

2. **Create the environment file:**
   ```bash
   cp backend/.env.example backend/.env
   ```
   *(Edit `backend/.env` according to the configuration section if needed, but defaults work for local dev.)*

3. **Start the containers:**
   ```bash
   docker compose up -d
   ```
   This will build the backend image (including native dependencies like WeasyPrint) and start the PostgreSQL database, Django server, and background worker.

4. **Verify it's running:**
   Navigate to `http://localhost:8000/api/public/verify/<cert_id>` (or use your API client).

## Deploying the Smart Contract

Before issuing certificates on the blockchain, you need to deploy the smart contract to Polygon Amoy.

1. **Install dependencies:**
   ```bash
   cd blockchain
   npm install
   ```

2. **Configure hardhat:**
   Ensure you have configured `hardhat.config.js` with your Alchemy/Infura RPC URL and a valid private key with Amoy MATIC.
   *Example: Use `.env` file inside `blockchain` folder.*

3. **Deploy:**
   ```bash
   npx hardhat run scripts/deploy.js --network amoy
   ```
   Note the deployed contract address.

## Configuration (.env)

Update your `backend/.env` with the deployed contract details:

```env
BLOCKCHAIN_RPC_URL=https://rpc-amoy.polygon.technology/
BLOCKCHAIN_CONTRACT_ADDRESS=<Deployed_Contract_Address>
BLOCKCHAIN_ISSUER_PRIVATE_KEY=<Your_Private_Key>
```

Make sure your backend server restarts to pick up these changes.

## Running the Tests

The test suite covers everything from authentication and PDF generation to blockchain integration and email notification tasks.

To run the complete test suite and generate a coverage report:

```bash
docker compose run --rm backend pytest --cov
```

This ensures zero manual/testnet interaction for unit tests, running against a localized test DB. All tests should pass without errors.
