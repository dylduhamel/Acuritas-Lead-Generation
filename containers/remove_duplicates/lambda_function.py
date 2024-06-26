from utils import remove_duplicates

# Lambda function entry point
def handler(event, context):
    try:
        remove_duplicates()

        return {
            'statusCode': 200,
            'body': 'Duplicates removed successfully.'
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'An error occurred: {str(e)}'
        }
