from src.batch.auto_input_suica.autoInput_Suica import AutoInput_Suica


def lambda_handler(event, context):
    return AutoInput_Suica().lambda_handler(event, context)
