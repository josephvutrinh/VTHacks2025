## Inspiration
One of Deloitte's challenges was to create a project related to "Student Performance Factors," which involves analyzing academic and extracurricular data to predict student performance and well-being. Picking classes has always been very time-consuming because you have to go through almost every professor to see which one's the best for you. This is especially important when a class is professor-dependent.

## What it does
Hokiefessor is an LLM powered by Databricks that answers all your questions related to professors and classes, recommending the best option for you.

## How we built it
We utilized Databricks' beta feature _Agent Bricks_ and trained our own LLM with webscraped data from Virginia Tech's Grade Distribution database, RateMyProfessor, and Reddit.

## Challenges we ran into
Training the LLM was one of the biggest challenges for our team because we were limited to $40 in free credits, which required a specific amount of data to elicit the best responses from our LLM. This was due to numerous attempts because the maximum amount of data was unknown, resulting in many hours lost. Another challenge we faced was connecting Databricks' backend to our project's frontend, as the Agentic AI feature we used from Databricks was relatively new and in beta, so there were not many resources online to assist us.

## Accomplishments that we're proud of
We were proud of all the data we were able to web-scrape to train our model. We pulled it from the VT public data commons, Reddit, and RateMyProfessor.
We were also proud of getting our LLM to work with fairly well accuracy, spitting out our pretty correct answers based on the results from our data.
We were also proud of our frontend, as it looks very clean and appealing to the users, as well as being simple

## What we learned
We learned that collecting too much data was inefficient, and it was more important to have quality data. When we had too much data, training our model took really long while having messy replies. Instead, we learned to just have less data but more controlled, and then train our model with good quality responses.

## What's next for Hokiefessor
In the future, we want to implement Hokiefessor into other majors, not just limited to engineering. We would want to have different options for choosing what field you are in so that the data and the replies are more accurate. This would make it so that all VT students would be able to benefit and make better choices for their classes.
