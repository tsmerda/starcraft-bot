# AI Development for StarCraft II

Welcome to the exciting journey of programming artificial intelligence for [StarCraft II](https://starcraft2.blizzard.com/en-us/), the popular real-time strategy game.
StarCraft II is free-to-play and available on Windows, Mac, and Linux platforms, making it accessible for AI enthusiasts and developers across different operating systems.

## Resources for Learning and Inspiration

As you embark on this adventure, here are some valuable resources to kickstart your AI project:

- The **Python-based StarCraft II Client** for AI development is an excellent starting point: Check out the repository at [BurnySc2/python-sc2](https://github.com/BurnySc2/python-sc2) for comprehensive guides and a plethora of [examples](https://github.com/BurnySc2/python-sc2/tree/develop/examples) to learn from.

- DeepMind's groundbreaking work on AI with their article, [AlphaStar: Mastering the real-time strategy game StarCraft II](https://deepmind.google/discover/blog/alphastar-mastering-the-real-time-strategy-game-starcraft-ii/), offers an in-depth look at how they trained a neural network to play StarCraft II at a high level.

- Explore AI tournaments, such as the ones hosted by the University of Olomouc, for a practical glimpse into competitive AI gameplay: [UPOL SC2 AI Cup](https://www.inf.upol.cz/sc2-ai-cup/).

- And more
  - https://eschamp.com/guides/how-to-quickly-start-with-a-terran-bot-in-python/
  - https://vinsloev.medium.com/conquer-the-galaxy-building-a-starcraft-2-ai-with-python-7925ce8d05aa
  - https://pythonprogramming.net/starcraft-ii-ai-python-sc2-tutorial/

## Setting Up Your Environment

### Vitual environment configuration

**Create a Virtual Environment and Install Dependencies**: Ensure that you have a clean workspace for your AI's development by creating a virtual environment and installing the necessary libraries.

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# For Windows:
.\.venv\Scripts\activate
# For macOS/Linux:
source .venv/bin/activate

# Install dependencies from the requirements.txt file
pip install -r requirements.txt
```

### Map Configuration for Bot Testing

To effectively test our AI bots, we will be using a simplified version of the game on a custom map named "Distributer." This map provides a controlled environment that is ideal for AI development and testing.

- **Downloading the Map**: Obtain the Distributer map from the following resource: [2022 - Agria Valley](https://www.inf.upol.cz/sc2-ai-cup/map/sc2-ai-cup-2022.SC2Map).

- **Installing the Map**: Once downloaded, the map file must be placed into the `Maps` directory of your StarCraft II installation. The default path on most systems is `C:\Program Files (x86)\StarCraft II\Maps`.

### Running a Demo Bot

To see a StarCraft II AI bot in action:

Execute the script StarCraftBot.py in your preferred IDE or command line interface.

```bash
python StarCraftBot.py
```
