#!/bin/bash

# Setup script for SimuExoV1 Memory System
# This script installs the required dependencies and sets up the memory system

set -e  # Exit on any error

echo "=== Setting up SimuExoV1 Memory System ==="

# Check if we're in the right directory
if [ ! -d "memory_system" ]; then
    echo "Error: memory_system directory not found. Please run this script from the SimuVerse_Backend directory."
    exit 1
fi

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r memory_system/requirements.txt

# Create a backup of the original main.py
if [ ! -f "main.py.bak" ]; then
    echo "Creating backup of main.py..."
    cp main.py main.py.bak
fi

# Apply the memory system patch
echo "Applying memory system patch to main.py..."
python -m memory_system.memory_patch

# Check if Docker is installed
if command -v docker >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1; then
    echo "Docker and docker-compose are installed."
    
    # Ask to start Docker containers
    read -p "Do you want to start the Qdrant vector database using Docker? (y/n): " start_docker
    
    if [[ $start_docker == "y" || $start_docker == "Y" ]]; then
        echo "Starting Qdrant container..."
        docker-compose -f docker-compose.memory.yml up -d
        echo "Waiting for Qdrant to start..."
        sleep 5
        
        # Check if Qdrant is running
        if curl -s http://localhost:6333/health > /dev/null; then
            echo "Qdrant is running successfully!"
            # Set environment variable for production use
            export USE_IN_MEMORY_VECTOR_STORE=0
        else
            echo "Warning: Qdrant may not be running properly. Will fall back to in-memory mode."
            export USE_IN_MEMORY_VECTOR_STORE=1
        fi
    else
        echo "Skipping Docker setup. Will use in-memory vector store."
        export USE_IN_MEMORY_VECTOR_STORE=1
    fi
else
    echo "Docker or docker-compose not found. Will use in-memory vector store."
    export USE_IN_MEMORY_VECTOR_STORE=1
fi

echo ""
echo "=== Memory System Setup Complete ==="
echo ""
echo "To start the SimuVerse backend with memory system:"
echo "python main.py"
echo ""
echo "To revert to the original main.py:"
echo "cp main.py.bak main.py"
echo ""
echo "Enjoy your enhanced agents with memories!"