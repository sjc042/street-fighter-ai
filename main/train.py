# Copyright 2023 LIN Yi. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import os
import sys

import retro
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.vec_env import SubprocVecEnv

from street_fighter_custom_wrapper import StreetFighterCustomWrapper

NUM_ENV = 16
LOG_DIR = 'logs'
TRAIN_NEW_MODEL = True   # Ciel: if true then train a new model, else finetune an exiting model
finetune_model_path = "trained_models\Level1_RyuVsGuile_4000000_steps.zip"  # Ciel: update if TRAIN_NEW_MODEL = False
STATE = "Champion.Level3.Chunli"    # Ciel: change the state the model is trained on
'''
states:
Champion.Level1.RyuVsDhalsim
Champion.Level1.RyuVsGuile
Champion.Level12.RyuVsBison
Champion.Level2.RyuVsKen
Champion.Level3.Chunli
'''

os.makedirs(LOG_DIR, exist_ok=True)

# Linear scheduler
def linear_schedule(initial_value, final_value=0.0):

    if isinstance(initial_value, str):
        initial_value = float(initial_value)
        final_value = float(final_value)
        assert (initial_value > 0.0)

    def scheduler(progress):
        return final_value + progress * (initial_value - final_value)

    return scheduler

def make_env(game, state, seed=0):
    def _init():
        env = retro.make(
            game=game, 
            state=state, 
            use_restricted_actions=retro.Actions.FILTERED, 
            obs_type=retro.Observations.IMAGE    
        )
        env = StreetFighterCustomWrapper(env)
        env = Monitor(env)
        env.seed(seed)
        return env
    return _init

def main():
    # Set up the environment and model
    game = "StreetFighterIISpecialChampionEdition-Genesis"
    game_state = STATE
    save_name_prefix = game_state.split(".")[1] + "_" + game_state.split(".")[2]
    env = SubprocVecEnv([make_env(game, state=game_state, seed=i) for i in range(NUM_ENV)])
    model_name = "ppo_sf2_{}.zip".format(save_name_prefix)
    print("save model as {}".format(model_name))

    if TRAIN_NEW_MODEL:
        # Set linear schedule for learning rate
        # Start
        lr_schedule = linear_schedule(2.5e-4, 2.5e-6)
        # Set linear scheduler for clip range
        # Start
        clip_range_schedule = linear_schedule(0.15, 0.025)
        model = PPO(
            "CnnPolicy", 
            env,
            device="cuda", 
            verbose=1,
            n_steps=512,
            batch_size=512,
            n_epochs=4,
            gamma=0.94,
            learning_rate=lr_schedule,
            clip_range=clip_range_schedule,
            tensorboard_log="logs"
        )
    else:
        # fine-tune
        lr_schedule = linear_schedule(5.0e-5, 2.5e-6)
        
        # fine-tune
        clip_range_schedule = linear_schedule(0.075, 0.025)
        # Load the model from file
        model_path = finetune_model_path

        # Load model and modify the learning rate and entropy coefficient
        custom_objects = {
            "learning_rate": lr_schedule,
            "clip_range": clip_range_schedule,
            "n_steps": 512
        }
        model = PPO.load(model_path, env=env, device="cuda", custom_objects=custom_objects)


    # Set the save directory
    save_dir = "trained_models"
    os.makedirs(save_dir, exist_ok=True)

    # Set up callbacks
    # Note that 1 timesetp = 6 frame
    checkpoint_interval = 31250 # checkpoint_interval * num_envs = total_steps_per_checkpoint
    checkpoint_callback = CheckpointCallback(save_freq=checkpoint_interval, save_path=save_dir, name_prefix=save_name_prefix)

    # Writing the training logs from stdout to a file
    original_stdout = sys.stdout
    log_file_path = os.path.join(save_dir, "training_log_{}.txt".format(save_name_prefix))
    with open(log_file_path, 'w') as log_file:
        sys.stdout = log_file
    
        model.learn(
            # Ciel: changed from 100,000,000 to 7,000,000
            total_timesteps=int(7000000), # total_timesteps = stage_interval * num_envs * num_stages (1120 rounds)
            callback=[checkpoint_callback]#, stage_increase_callback]
        )
        env.close()

    # Restore stdout
    sys.stdout = original_stdout

    # Save the final model
    model.save(os.path.join(save_dir, model_name))

if __name__ == "__main__":
    main()
