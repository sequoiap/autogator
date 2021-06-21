import autogator.dataCache

# Get the Data Cache
cache = autogator.dataCache.DataCache.get_instance()
cache.load_configuration()
mot = cache.motion.get_instance()

# Save and set a new step size
original_step_size = mot.r_mot.jog_step_size
mot.r_mot.jog_step_size = 10

# Perform two Clockwise Rotations
input("Press Enter For Next Rotation: ")
mot.concentric_rotatation()
input("Press Enter For Next Rotation: ")
mot.concentric_rotatation()

# Perform two Counter-Clockwise Rotations to return to the original position
input("Press Enter For Next Rotation: ")
mot.concentric_rotatation("backward")
input("Press Enter For Next Rotation: ")
mot.concentric_rotatation("backward")

# Reset the step size to original
mot.r_mot.jog_step_size = original_step_size
