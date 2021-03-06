#!/usr/bin/env python

import webapp2
import time
import logging
import json

from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from utils import to_json
from models.trip import Trip
from models.user import User
from wrappers.firebase import FirebaseWrapper

class TripHandler(webapp2.RequestHandler):
    def get(self, trip_id):
        if trip_id is None:
            self.response.status_int = 400
            self.response.write({'error': 'Unable to retrieve trip - Missing trip id'})
            return

        parent = ndb.Key(urlsafe=trip_id).parent().get()
        trip = ndb.Key(urlsafe=trip_id).get()

        request = {
            "user_id" : parent.key.urlsafe(),
            "trip_id" : trip_id
        }

        fb_wrapper = FirebaseWrapper()
        fb_response = fb_wrapper.firebase_get(request)

        if fb_response.status_code == 200:
            response = {
                "trip_id" : trip_id,
                "owner"   : parent.key.urlsafe(),
                "name"    : trip.name,
            }
            entries = []
            content = json.loads(fb_response.content)
            for entry in content:
                entries.append({ entry : content[entry]})

            response['entries'] = entries

            self.response.status_int = 200
            self.response.write(response)
            return

    def post(self):
        """
        POST /trip

        Creates a Trip for the user
        """
        request = to_json(self.request.body)

        if request.get('name') is None:
            self.response.status_int = 400
            self.response.headers['Access-Control-Allow-Origin'] = "http://www.myvoyagr.co"
            self.response.write({'error' : 'Missing name of trip'})
            return
        elif request.get('email') is None:
            self.response.status_int = 400
            self.response.headers['Access-Control-Allow-Origin'] = "http://www.myvoyagr.co"
            self.response.write({'error' : 'Missing email that the trip will be associated with'})
            return
        elif request.get('file_ids') is None:
            self.response.status_int = 400
            self.response.headers['Access-Control-Allow-Origin'] = "http://www.myvoyagr.co"
            self.response.write({'error' : 'Missing file_ids'})
            return
        elif request.get('access_token') is None:
            self.response.status_int = 400
            self.response.headers['Access-Control-Allow-Origin'] = "http://www.myvoyagr.co"
            self.response.write({'error' : 'Missing access token'})
            return
        else:
            # Check that user model exists
            user = User.query(User.email==request.get('email')).get()
            if user is None:
                self.response.status_int = 400
                self.response.headers['Access-Control-Allow-Origin'] = "http://www.myvoyagr.co"
                self.response.write({'error' : 'Error retrieving user'})
                return

            # Create a trip with that user model as ancestor
            trip = Trip(parent=user.key)
            trip.name = request.get('name')
            trip.put()

            # Save on FB
            fb_wrapper = FirebaseWrapper()

            # Go through each file id and get the file information
            entities = []
            access_token = request.get('access_token')

            for t_id in request.get('file_ids'):
                result = urlfetch.fetch(url="https://www.googleapis.com/drive/v2/files/{}".format(t_id),
                    method=urlfetch.GET,
                    headers={'Authorization' : 'Bearer {}'.format(access_token)}
                )
                data = to_json(result.content)

                if result.status_code == 200:
                    payload = {
                        "lat": data.get('imageMediaMetadata').get('location').get('latitude') if data.get('imageMediaMetadata').get('location') else 0.0,
                        "long": data.get('imageMediaMetadata').get('location').get('longitude') if data.get('imageMediaMetadata').get('location') else 0.0,
                        "thumbnail_link": data.get('thumbnailLink'),
                        "description" : data.get('description'),
                        "created" : data.get('createdDate'),
                        "created_on_firebase": int(time.time())
                    }

                    request = {
                        "user_id" : user.key.urlsafe(),
                        "trip_id" : trip.key.urlsafe(),
                        "payload" : json.dumps(payload)
                    }

                    fb_response = fb_wrapper.firebase_post(request)

                    if fb_response.status_code != 200:
                        logging.error("Error saving file {} to FB".format(t_id))
                        logging.error(fb_response.content)
                    else:
                        entities.append({ json.loads(fb_response.content).get('name') : payload })
                else:
                    logging.error("Unable to retrieve file {}".format(t_id))
                    logging.error(result.content)

            response = {
                "trip_id" : trip.key.urlsafe(),
                "owner"   : user.key.urlsafe(),
                "name"    : trip.name,
                "entities" : entities
            }

            self.response.status_int = 200
            self.response.headers['Access-Control-Allow-Origin'] = "http://www.myvoyagr.co"
            self.response.write(response)
            return

