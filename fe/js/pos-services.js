var posmonServices = angular.module('posmonServices', ['ngResource']);

posmonServices.factory('Config', ['$resource',
  function($resource) {
    return $resource('json/config');
  }]);

posmonServices.factory('Tower', ['$resource',
  function($resource) {
    return $resource('json/towers/:towerId');
  }]);

posmonServices.factory('Search', ['$resource',
  function($resource) {
    return $resource('json/search/:searchText');
  }]);
