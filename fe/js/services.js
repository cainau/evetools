var soundServices = angular.module('soundServices', ['ngResource']);

soundServices.factory('Config', ['$resource',
  function($resource) {
    return $resource('json/config');
  }]);

soundServices.factory('Payment', ['$resource',
  function($resource) {
    return $resource('json/payments/:paymentId');
  }]);

soundServices.factory('Kill', ['$resource',
  function($resource) {
    return $resource('json/kills/:killId');
  }]);

soundServices.factory('Character', ['$resource',
  function($resource) {
    return $resource('json/characters/:characterId');
  }]);

soundServices.factory('Tower', ['$resource',
  function($resource) {
    return $resource('json/towers/:towerId');
  }]);

soundServices.factory('Search', ['$resource',
  function($resource) {
    return $resource('json/search/:searchText');
  }]);
