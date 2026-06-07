from src.batch.auto_csv_input_suica.autoCsvInput_Suica import AutoCsvInput_Suica


def lambda_handler(event, context):
    return AutoCsvInput_Suica().lambda_handler(event, context)
