# Project: emergent sparsity in unsupervised learning by disagreement


Experiments with learning by disagreement, tested in robot_arm environment.

For more details please contact vclay at numenta dot com.

### Installation

Create a new environment with python 3.7:
`conda create -n <environment_name> python=3.7`
`conda activate <environment_name>`

To install nupic.embodied from source, on nupic.embodied root run: `pip install -e .`

To install robot_arm specific requirements, on projects/robot_arm run: `pip install -r requirements.txt`

For proper logging, make sure to set your `WANDB_API_KEY` environment variable. See [wandbdoc](https://docs.wandb.ai/guides/track/advanced/environment-variables). If you don't have an account, create (a free) one to get an API key.

### Execution

To run an experiment, first define a new experiment in a python module under the folder experiments. Please follow the example of other configs already created.

To run, on projects/robot_arm call `python run.py -e <experiment_name>`