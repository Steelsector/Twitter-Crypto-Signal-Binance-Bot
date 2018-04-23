import utils
import time
import tweepy
import binance_utils

"""

Monitors someone's tweets for specific words.
If it contains those words, it then looks for a coin symbol in the
tweet and buys it if it can be bought on binance. Then
waits to sell the coin at a profit.

"""

utils.print_and_write_to_logfile('STARTING...')

# Get twitter id's from http://gettwitterid.com
twitter_user_ids_to_follow = ['759916693']
twitter, auth = utils.get_twitter_account()

binance = binance_utils.get_binance_account()
binance_coins = binance_utils.get_binance_buyable_coins(binance)

ignored_coins = utils.get_ignored_coins()

words_to_look_for = utils.get_words_to_look_for()

seconds_before_checking_binance = 30

one_minute_in_milliseconds = 60000

##################

# Buying Variables
# .01 means 1%

##################

# Percent above current sell price to place buy order
limit_buy_order_percent = .01

# Cancel buy order if it hasn't sold and the price is this percent more.
limit_buy_order_cap_percent = .03

###################

# Selling Variables
# .01 means 1%

###################

# Desired percentage profit
limit_sell_order_desired_percentage_profit = .05

# Sell if the price drops this far below bought price
limit_sell_order_percent_too_low = -.02

# Percent below current price to place sell order
limit_sell_order_stop_loss_percent = -.01

# Percent dropped below last price after we have reached our goal
# making it time to sell
limit_sell_percent_down_to_sell = -.01

# Place a sell order this percent less than the current price
limit_sell_percent_lower_than_cur_price = -.01

"""

Puts in a buy order at a price that is limit_buy_order_percent above the current price
Then waits until the order has been filled.

"""


def handle_buying(market):
    status, bought_price, order_id, amount_bought = binance_utils.limit_buy_from_binance(binance, market,
                                                                                         limit_buy_order_percent)

    cancel_price = bought_price * (1 + limit_buy_order_cap_percent)

    if status != 'FILLED':
        while True:
            order = binance.get_order(
                symbol=market,
                orderId=order_id)

            status = order['status']

            amount_bought = float(order['executedQty'])

            if status == "FILLED":
                break

            cur_price = binance_utils.get_most_recent_sell_order_price(binance, market)

            if cur_price > cancel_price:
                break

            time.sleep(seconds_before_checking_binance)

    return bought_price, amount_bought


def wait_until_time_to_sell(bought_price, market):
    percentage_change = 0
    reached_goal = False
    while True:
        cur_price = binance_utils.get_most_recent_buy_order_price(binance, market)
        percentage_change = utils.percent_change(bought_price, cur_price)

        if percentage_change >= limit_sell_order_desired_percentage_profit:
            reached_goal = True

        if percentage_change < limit_sell_percent_down_to_sell and reached_goal == True:
            break

        time.sleep(seconds_before_checking_binance)


"""

Waits until the price has gone up

limit_sell_order_desired_percentage_profit

percent and then dropped

limit_sell_percent_down_to_sell

percent. Then puts in a sell order for

limit_sell_percent_lower_than_cur_price

less than the current price.


"""


def handle_selling(bought_price, market, amount_bought):

    wait_until_time_to_sell(bought_price, market)

    status, order_id = binance_utils.limit_sell_on_binance(binance, market, amount_bought, bought_price,
                                                           limit_sell_percent_lower_than_cur_price)
    amount_sold = 0
    while status != 'FILLED':
        cur_price = binance_utils.get_most_recent_buy_order_price(binance, market)

        order = binance.get_order(
            symbol=market,
            orderId=order_id)

        status = order['status']
        float(order['executedQty'])

        percent_change = utils.percent_change(bought_price, cur_price)

        # Coin is going down too much, cancel order and sell lower
        if percent_change < limit_sell_order_percent_too_low:
            binance.cancel_order(
                symbol=market,
                orderId=order_id)

            # Sell at a limit_sell_order_stop_loss_percent lower than the current_price
            order_placed, order_id = binance_utils.limit_sell_on_binance(binance, market, amount_bought - amount_sold,
                                                                         cur_price,
                                                                         limit_sell_order_stop_loss_percent)
        time.sleep(seconds_before_checking_binance)


class MyStreamListener(tweepy.StreamListener):

    # Called when there is a new status
    def on_status(self, status):
        tweet_time = int(status.timestamp_ms)
        cur_time = int(round(time.time() * 1000))

        # Tweets will queue while we are waiting to sell
        # and we don't want to buy on old data
        if cur_time - tweet_time < one_minute_in_milliseconds:

            if utils.contains_words_to_look_for(status.text, words_to_look_for):

                coin_name = utils.get_coin_name_in_text(status.text, ignored_coins, binance_coins)

                if coin_name:
                    utils.print_and_write_to_logfile(coin_name + " in tweet: " + status.text)
                    market = binance_coins[coin_name][0]

                    bought_price, amount_bought = handle_buying(market)

                    if amount_bought > 0:
                        handle_selling(bought_price, market, amount_bought)


# Begin Listening for new Tweets
streamListener = MyStreamListener()
stream = tweepy.Stream(auth, streamListener)
stream.filter(follow=twitter_user_ids_to_follow)