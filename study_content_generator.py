from dotenv import load_dotenv 
from pytube import YouTube
import os
import requests
import time
import openai
import re
import textwrap
from utility import write, read, read_binary

load_dotenv()
# TODO - create a .env file with two keys: ASSEMBLY_KEY and OPENAI_KEY
ASSEMBLY_KEY = os.getenv("ASSEMBLY_KEY")
openai.api_key = os.getenv("OPENAI_KEY")

# - - - - - - - - - - -PATHS - - - - - - - - - - #
# prompts 
SUMMARIZE_PROMPT= "prompts/summarize_prompt.txt"
RECALL_PROMPT = "prompts/recall_questions_prompt.txt"
# logs
TRANSCRIPTS_LOG = "logs/transcripts/"
SUMMARIES_LOG = "logs/summaries/"
RECALL_LOG = "logs/recall_questions/"
VIDEOS_LOG = "logs/videos/"

# NOTE: run Install Certificates.command from Python directory on MacOS

# Downloads the YouTube video at the specified url.
# link - the link to download the video from
# returns a dictionary with the title of the video and length in seconds
# error if url is not valid or no internet connection (URLError, ) 
def download_video(link):
    yt = YouTube(link)
    stream = yt.streams.filter(progressive=True, file_extension="mp4").first()
    path = stream.download(VIDEOS_LOG)
    title = "".join([c for c in yt.title if c.isalpha() or c.isdigit() or c==' ']).rstrip()

    # log info to console
    print(f"VIDEO: {title}\nSuccessfully downloaded\nLENGTH: {yt.length}s")

    return {"title": title, "length": yt.length, "path": path}


# Loads a local audio/video file to AssemblyAI API.
# filename - the path to the file 
# returns the upload url that the API can use to trascribe the audio/video
def upload(filename):
    response = requests.post('https://api.assemblyai.com/v2/upload',
      headers={'authorization': ASSEMBLY_KEY},
      data=read_binary(filename))
    url = response.json()["upload_url"]

    # log info to console
    print(f"Uploaded file to: {url}")
    return url


# Transcribes the video at the url. Waits for 15% of the video duration before
# checking transcription status. If trasncript not ready waits until 30% of video duration
# has elapsed. See https://www.assemblyai.com/docs/
def transcribe(upload_url, duration):
  # post request to transcribe data at the specified url 
  response = requests.post(
    "https://api.assemblyai.com/v2/transcript",
    json={"audio_url": upload_url}, 
    headers={"authorization": ASSEMBLY_KEY, "content-type": "application/json"})
  id = response.json()["id"]
  print(f"Posted request for transcript\nRequest id: {id}")

  # wait for transcription to yield results
  sleep_value = duration * 0.15
  print(f"Maximum wait time: {sleep_value * 2}s ({round(sleep_value * 2 / 60, 2)}mins)")
  for tries in range(2):
    # log info to console
    print(f"Waiting for {sleep_value}s ({round(sleep_value / 60, 2)}mins)")

    time.sleep(sleep_value)
    response = requests.get(
      "https://api.assemblyai.com/v2/transcript/" + id,
      headers={"authorization": ASSEMBLY_KEY})
    json = response.json()
    if json["status"] == "completed":
      print("Trancript completed")
      return json["text"]

  raise TimeoutError("Timed out attempting to transcribe file")


# Summarizes the specified content using GPT3 API and returns the result.
# PRECONDITION: the prompt and completion must not exceed the token limit 
# content - the text to summarize
# temperature - the measure of determinism of the completion 
# max_tokens - the max size of the completion
def summarize(content, temperature=1, max_tokens=400):
  response = openai.Completion.create(
    model="text-davinci-002",
    prompt= read(SUMMARIZE_PROMPT).replace("<<<CONTENT>>>", content),
    temperature=temperature,
    max_tokens=max_tokens,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0
  )
  return re.sub("\\s+", " ", response["choices"][0]["text"])


# Summarize text of arbitrary length by tokenizing content into smaller
# chunks and contatenating the result. 
# See: https://docs.python.org/3/library/textwrap.html
def summarize_large(content, temperature=1, max_tokens=400, chunk_size=8000):
  print("Getting ready to create summary. This may take a few seconds...")
  tokens = textwrap.wrap(content, width=chunk_size)

  summary = ""
  for i, token in enumerate(tokens):
    print(f"Summarizing chunk: {i + 1}")
    summary += summarize(token, temperature, max_tokens) + "\n\n"
    # sleep(5)
  print("Summarization complete")
  return summary


# Create study questions and answers.
# PRECONDITION: the prompt and completion must not exceed the token limit 
# content - the text to create study Q%A from
# temperature - the measure of determinism of the completion 
# max_tokens - the max size of the completion
def generate_recall_questions(content, temperature=0.5, max_tokens=256):
  response = openai.Completion.create(
    model="text-davinci-002",
    prompt= read(RECALL_PROMPT)
      .replace("<<<CONTENT>>>", content),
    temperature=temperature,
    max_tokens=max_tokens,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0
  )
  return response["choices"][0]["text"].strip()


# Create study questions and answers for an arbitrarily large input.
# The questions and answers are generated for each chunk and consolidated into
# one string with sections of Q&A for each chunk
def get_recall_questions(content, temperature=0.5, max_tokens=256, chunk_size=8000):
  print("Getting ready to generate study Q&A. This may take a few seconds...")
  tokens = textwrap.wrap(content, width=chunk_size)

  answer = ""
  for i, token in enumerate(tokens):
    print(f"Generating Q&A for chunk: {i + 1}")
    completion = generate_recall_questions(token, temperature, max_tokens)
    answer += f"--- Section {i + 1} ---\n{completion}\n\n"
    # sleep(5)

  print("Recall question generation complete")
  return answer.strip()


if __name__ == "__main__":
  # Demo program that generates study content for user-specified YouTube videos and logs
  # the results of intermediate steps and the main outputs to text files in the 
  # logs directory
  def main():
      link = input("Enter a link to a YouTube video you would like to create study content for (Q to QUIT): ")
      if link.upper() == "Q":
        print("QUITTING...")
      else:
          try:
            video_info = download_video(link)
            TITLE = video_info["title"]
            LENGTH = video_info["length"] # in seconds

            url = upload(video_info["path"])
            transcript = transcribe(url, LENGTH)
            write(f"{TRANSCRIPTS_LOG}{TITLE}.txt", transcript)

            summary = summarize_large(transcript)
            write(f"{SUMMARIES_LOG}{TITLE}.txt", summary)

            recall_questions = get_recall_questions(transcript)
            write(f"{RECALL_LOG}{TITLE}.txt", recall_questions)

            # COMPRESS SUMMARY option
            compression = 1
            compress = True
            while compress:
              user_input = input("Compress summary? (Y/N) ")
              if user_input.upper() == "Y":
                summary = summarize_large(summary)
                write(f"{SUMMARIES_LOG}{TITLE} (compressed {compression}).txt", summary)
                compression += 1
              else:
                compress = False

            print("All operations complete")
              
          except Exception as e:
            print(e)
            print("Something went wrong :( Please try again.")
            
  main()