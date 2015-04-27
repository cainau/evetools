var srpServices = angular.module('srpServices', ['ngResource']);

srpServices.factory('Config', ['$resource',
  function($resource) {
    return $resource('json/config');
  }]);

srpServices.factory('Payment', ['$resource',
  function($resource) {
    return $resource('json/payments/:paymentId');
  }]);

srpServices.factory('Kill', ['$resource',
  function($resource) {
    return $resource('json/kills/:killId');
  }]);

srpServices.factory('Character', ['$resource',
  function($resource) {
    return $resource('json/characters/:characterId');
  }]);

srpServices.factory('Search', ['$resource',
  function($resource) {
    return $resource('json/search/:searchText');
  }]);
