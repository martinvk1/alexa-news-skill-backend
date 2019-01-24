import logging
import psycopg2
import re
import requests
import random
from datetime import datetime

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model.ui import SimpleCard
from ask_sdk_model import Response

article_index = 0
possible_headlines = []

sb = SkillBuilder()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Publisher Configuration
publisher_name = 'Speech Kit'
project_id = 1279

blacklist = ['from', 'by'] + publisher_name.split()
uri = os.environ.get('PSQL_DB')

# General function for fetching news from the database
def psql_fetch(project_id, n):
	cmd = '''SELECT title, body, published_at from podcasts WHERE project_id={} and title<>'' and body<>'' ORDER BY published_at DESC LIMIT {};'''.format(project_id, n)
	address = uri
	conn = psycopg2.connect(address, sslmode='require')
	cur = conn.cursor()
	cur.execute(cmd)
	results = cur.fetchall()
	conn.close()
	return results
	

def ssml_to_text(ssml):
    return ''.join((re.sub('<.*?>','',ssml).split('{|||}'))).replace('"',"'")


def ssml_remove_unsupported_tags(ssml):
    chunks = ssml.split('{|||}')
    return ''.join([re.sub('<amazon:breath.*?/>','', chunk)[7:-8] for chunk in chunks])


def create_article_ssml(handler_input, article_index, timestamp = False):
    article = articles[article_index]
    date = article[2]
    weekdays = {0:'Monday', 1:'Tuesday', 2:'Wednesday', 3:'Thursday', 4:'Friday', 5:'Saturday', 6: 'Sunday'}
    
    if datetime.now().day - date.day < 8:
        if date.day == datetime.now().day:
            day = 'today'
        elif date.day == datetime.now().day - 1:
            day = 'yesterday'
        else:
            day = 'on ' + weekdays[date.weekday()]
    else:
        handler_input.response_builder.speak('Welcome to {}. Unfortunately, there are no recent stories here.')
        return handler_input.response_builder.response
    
    intro = 'Welcome to {}. Here is the latest story, published {}.'.format(publisher_name, day) if timestamp else ''
    sound = '<audio src="https://s3.eu-west-2.amazonaws.com/speechkit-alexa-skill-sounds/alexa_sound_cropped.mp3"/>'
    beep = '<audio src="https://s3.eu-west-2.amazonaws.com/speechkit-alexa-skill-sounds/alexa_beep.mp3"/>'
    title = ssml_remove_unsupported_tags(article[0])
    small_pause = '<break strength="medium">'
    body = ssml_remove_unsupported_tags(article[1])
    outro = 'To listen to the next article, say Alexa, next.'

    content = intro + sound + title + beep + body + outro

    if len(content) > 8000:
        handler_input.response_builder.speak('The SSML is too long')
    else:
        handler_input.response_builder.speak(content)

    return handler_input.response_builder.response
    

def get_headlines_ssml(handler_input):
    intro = 'Here are the latest headlines from {}. '.format(publisher_name)
    global possible_headlines
    possible_headlines = [ssml_to_text(articles[n][0]).lower() for n in range(10)]
    titles_enumerated = ' '.join([str(n+1) + ' ' + ssml_remove_unsupported_tags(articles[n][0]) for n in range(10)])
    outro = 'To listen to any of these articles, you refer to their number'
    
    content = intro + titles_enumerated + outro

    if len(content) > 8000:
        handler_input.response_builder.speak('The SSML is too long')
    else:
        handler_input.response_builder.speak(content)


    return handler_input.response_builder.response
    
    
def headline_choice(headlines, search_query):
    
    def levenshtein(s1, s2):
        if len(s1) < len(s2):
            return levenshtein(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]
    
    chosen_index = 0
    query = search_query
    min_distance = len(query)
    for index, t in enumerate(headlines):
        edit_distances = []
        if len(query) > len(t):
            t, query = query, t
        if len(query) == len(t):
            t += ' '
        for i in range(0, len(t) - len(query), 2):
            substring = t[i:i+len(query)]
            edit_distances.append(levenshtein(query, substring))
        if min(edit_distances) < min_distance:
            min_distance = min(edit_distances)
            chosen_index = index
        query = search_query
                
    return chosen_index


### Custom Handlers

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)
    def handle(self, handler_input):
        global article_index
        article_index = 0
        return create_article_ssml(handler_input, article_index, timestamp=True)
        
        
class ReadNewsHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("ReadNews")(handler_input)
    def handle(self, handler_input):
        global article_index
        article_index = 0
        return create_article_ssml(handler_input, article_index, timestamp=True)
        

class NextArticleHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("NextArticle")(handler_input)
    def handle(self, handler_input):
        global article_index
        article_index += 1
        return create_article_ssml(handler_input, article_index)
        
        
class PreviousArticleHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("PreviousArticle")(handler_input)
    def handle(self, handler_input):
        global article_index
        article_index -= 1
        return create_article_ssml(handler_input, article_index)

       
class FirstArticleHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("FirstArticle")(handler_input)
    def handle(self, handler_input):
        global article_index
        article_index = 0
        return create_article_ssml(handler_input, article_index)
        
        
class ListNewsHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("ListNews")(handler_input)
    def handle(self, handler_input):
        return get_headlines_ssml(handler_input)
        

class RequestHeadlineHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("RequestHeadline")(handler_input)
    def handle(self, handler_input):
        index = 0
        slots = handler_input.request_envelope.request.intent.slots
        topic = slots['topic'].value if 'topic' in slots else None
        longtopic = slots['longtopic'].value if 'longtopic' in slots else None
        number = slots['number'].value if 'number' in slots else None
        
        if longtopic:
            index = headline_choice(possible_headlines, longtopic)
        if topic:
            index = headline_choice(possible_headlines, topic)
        
        cardinal_idx = {'first':0, 'second':1, '3rd':2, '4th':3, '5th':4,
                        '6th':5, '7th':6, '8th':7, '9th':8, '10th':9}
        
        if number:
            if number in cardinal_idx:
                index = cardinal_idx[number]
            if number.isdigit():
                index = int(number) - 1
            
        global article_index
        article_index = index
  
        return create_article_ssml(handler_input, article_index, timestamp = False)
        

### Built-in Handlers

class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speech_text = "You can skip to the next story or ask for a list to choose from."

        handler_input.response_builder.speak(speech_text)
        return handler_input.response_builder.response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("AMAZON.CancelIntent")(handler_input) or
                is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speech_text = ""

        handler_input.response_builder.speak(speech_text)
        return handler_input.response_builder.response


class FallbackIntentHandler(AbstractRequestHandler):
    """AMAZON.FallbackIntent is only available in en-US locale.
    This handler will not be triggered except in that locale,
    so it is safe to deploy on any locale.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speech_text = "Sorry, I can't help you with that."
        handler_input.response_builder.speak(speech_text)
        return handler_input.response_builder.response


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speech_text = "Goodbye!"
        handler_input.response_builder.speak(speech_text)
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Catch all exception handler, log exception and
    respond with custom message.
    """
    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speech = "Sorry, there was some problem. Please try again or ask me for help!"
        handler_input.response_builder.speak(speech).ask(speech)

        return handler_input.response_builder.response


sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(NextArticleHandler())
sb.add_request_handler(PreviousArticleHandler())
sb.add_request_handler(FirstArticleHandler())
sb.add_request_handler(ReadNewsHandler())
sb.add_request_handler(ListNewsHandler())
sb.add_request_handler(RequestHeadlineHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

sb.add_exception_handler(CatchAllExceptionHandler())

handler = sb.lambda_handler()

articles = psql_fetch(project_id, n=100)
