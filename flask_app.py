import json
import shopify
from flask import Flask, request
from twilio.rest import Client
from datetime import datetime, timedelta


shopify_config = {
    'API_KEY': 'your_api_key',
    'API_PASSWORD': 'your_api_password',
    'STORE_NAME': 'your_store_name.myshopify.com',
}
shopify.Session.setup(api_key=shopify_config['API_KEY'], 
                      secret=shopify_config['API_PASSWORD'])
shopify.ShopifyResource.set_site(f"https://{shopify_config['STORE_NAME']}")


app = Flask(__name__)

@app.route('/order_webhook', methods=['POST'])
def order_webhook():
    # Extract the order data from the webhook payload
    data = request.data.decode('utf-8')
    payload = json.loads(data)
    order_data = payload['data']
    
    # Extract the relevant order data and process it
    order_dict = {
        'id': order_data['id'],
        'name': order_data['name'],
        'email': order_data['email'],
        'total_price': order_data['total_price'],
        'created_at': order_data['created_at'],
        # Add any additional fields you want to include here
    }
    process_order(order_dict)
    
    return 'Webhook received', 200
  
 
# Define a function to retrieve order data
def get_orders(days_back=7):
    # Calculate the start and end dates for the order query
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    # Build the order query and retrieve the orders
    orders = shopify.Order.find(created_at_min=start_date, created_at_max=end_date, limit=100)
    
    # Extract the relevant order data and return it as a list of dictionaries
    order_data = []
    for order in orders:
        order_dict = {
            'id': order.id,
            'name': order.name,
            'email': order.email,
            'total_price': order.total_price,
            'created_at': order.created_at,
            # Add any additional fields you want to include here
        }
        order_data.append(order_dict)
    return order_data

# Example usage: retrieve all orders created in the past 7 days
orders = get_orders(days_back=7)
print(orders)

def process_order(order_dict):
    # Send the order data as a WhatsApp message
    account_sid = 'your_account_sid'
    auth_token = 'your_auth_token'
    client = Client(account_sid, auth_token)

    message = client.messages.create(
        from_='whatsapp:+14155238886',
        body=f"New order received!\nOrder ID: {order_dict['id']}\nCustomer name: {order_dict['name']}\nTotal price: {order_dict['total_price']}",
        to='whatsapp:+1234567890'
    )

    print(f"Sent message to {message.to}: {message.body}")

if __name__ == '__main__':
    app.run(debug=True)
