# Nestswipe project
This is an agentic application that has several part

## Part 1 - Storing housings offers
It should be able to read user email to analyse email with housing offers (for instance those coming from seloger.com or pap.fr) using an LLM API.
We could start the project simply by only looking at email coming from specific sources, and run the LLM oly on those to reduce the cost.
We should start simply by only support gmail for now, extension will be added later in the project
Once an housing offer has been identified it should be stored in a backend with its key attributes: 
- Number of squared meter
- Price per squared meter
- Total price
- Number of bedrooms
- Location (city and district, for instance in Paris it could be Paris, 16eme nord, close to Passy)
- A link to the initial offer
- Photos
It is important to be able to dinstinguish between new housing (first time seen by the system) and old housing just updated. We can rely on photo hash or other technique to try to detect this. Prices should be tracked for updated housing so we can see the history of prices in Part 3

## Part 2 - Selecting interesting housings
The user should be able to login into a UI (web for now). On his first page he should view the newest housing coming from part 1. I imagine a UI similar to grinder where we would housing by housing with 2 button, one to ignore, one to add in the backlog of interesting housing
It is important to have a sneak peak of the housing so the user should be able to see the pictures immediatly with the most important caracteristics.
It is important to be able to dinstinguish between new housing (first time seen by the system) and old housing just updated. The part 2 shall only present new housing

## Part 3 - Edit and comment interesting housings
The user should be able to navigate in the UI to a my favorite section where all interested housing will be listed here. 
First view should be a list of housing with their main characteristics (1 photo, 1 short description, total price, number of squared meter). On each item it should be able to add comments so that we can come back to this housing later and read the history. 
User should be able to delete an interesting housing 

## Authentification
User MUST be authenticated to be able to log into the system and use it. 
For now we should only support google login for now, and add the read email scope so that the agent can read user email with this token.

## Social Network
User should be able to invite an other user of this app (using user email). Once the invitation is accepted users share all the interesting housings and can both comments (they have the same Part 2 view)

## Layout
### Header
4 buttons/links => Part 2, Part 3, Settings, Logout
### Settings
User should be able to configure its LLM Api Key (for now we should only support OpenAI)

