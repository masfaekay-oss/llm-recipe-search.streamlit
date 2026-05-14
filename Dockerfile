# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory in the container to /semantic_search_streamlit
WORKDIR /semantic_search_streamlit

# Copy the current directory contents into the container at /semantic_search_streamlit
COPY . /semantic_search_streamlit

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8502 available to the world outside this container (Change port if required)
EXPOSE 8502

# Run app.py when the container launches
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.port=8502", "--server.address=0.0.0.0"]