# skipera
Module to facilitate skipping Coursera (https://www.coursera.org/) videos and assessments.

## Why?
Skipera assists in automatically skip irrelevant MOOC courses which are made mandatory by universities. 
Many of such courses are allotted directly by the university as credit fillers and are not in the interest of the student. The progress of the completion of these courses is tracked by the university and credits are allotted.

## How?
Skipera makes use of the Coursera web API and completes the videos + reading materials.
Graded assessments are completed with the assistance of an LLM API. Skipera currently supports the Perplexity API.

## How to use
* A sample config is provided in the repo. For now, cookie auth has been implemented since login requires reCaptcha.
* Add your cookies to the config as key-value pairs (simple python dict). The presence of the "CAUTH" cookie is important. (https://github.com/serv0id/skipera/issues/1)
* `python3 main.py course-slug` where course-slug is present in the Coursera Course URL. Example: "introduction-psychology" (without the quotes) if the URL is https://www.coursera.org/learn/introduction-psychology/home/module/2.
