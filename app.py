#Send shopify order data to whatsapp using Shopify weebhook as order come

import shopify
from datetime import datetime, timedelta

# Set up your Shopify API credentials
shopify_config = {
    'API_KEY': 'your_api_key',
    'API_PASSWORD': 'your_api_password',
    'STORE_NAME': 'your_store_name.myshopify.com',
}
shopify.Session.setup(api_key=shopify_config['API_KEY'], 
                      secret=shopify_config['API_PASSWORD'])
shopify.ShopifyResource.set_site(f"https://{shopify_config['STORE_NAME']}")

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
