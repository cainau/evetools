var posmonControllers = angular.module('posmonControllers', [
  'soundServices', 'ui.bootstrap'
]);

function romanize(num) {
    if (!+num)
        return false;
    var digits = String(+num).split("");
    var key = ["","C","CC","CCC","CD","D","DC","DCC","DCCC","CM",
               "","X","XX","XXX","XL","L","LX","LXX","LXXX","XC",
               "","I","II","III","IV","V","VI","VII","VIII","IX"];
    var roman = "";
    var i = 3;
    while (i--)
        roman = (key[+digits.pop() + (i * 10)] || "") + roman;
    return Array(+digits.join("") + 1).join("M") + roman;
}

function timeStr(hours, useDays) {
    if (hours >= 24 && useDays) {
        days = Math.floor(hours / 24);
        hours -= 24 * days;
        return days + "d " + hours + "h";
    }
    return hours + "h";
}

function processTower(tower) {
    tower.location = romanize(tower.planet) + "-" + String(tower.moon);
    tower.errors = [];
    fuelHours = Math.floor(tower.fuel_qty / tower.fuel_hourly_usage);
    minHours = fuelHours;
    tower.fuel_time = timeStr(fuelHours, true);
    if (fuelHours < 24) {
      tower.fuel_class = 'bg-danger';
    } else if (fuelHours < 72) {
      tower.fuel_class = 'bg-warning';
    } 
    strontHours = Math.floor(tower.stront_qty / tower.stront_hourly_usage);
    tower.stront_time = timeStr(strontHours, false);
    if (strontHours < 29 || strontHours > 43) {
      tower.stront_class = 'bg-danger';
      tower.errors.push('Stront time of ' + strontHours + ' hours is outside the standard range.');
    }
    tower.input_volume = 0;
    tower.output_volume = 0;
    tower.silos.forEach(function(silo) {
        if (!silo.content_type_id) {
            silo.content_type_id = silo.silo_type_id;
            silo.content_type_name = "Empty " + silo.silo_type_name;
        }
        silo.percent = Math.round(100 * silo.qty * silo.content_size / silo.capacity);
        if (silo.hourly_usage) {
            qty = silo.input ? silo.qty : Math.floor(silo.capacity / silo.content_size) - silo.qty;
            siloHours = Math.floor(qty / Math.abs(silo.hourly_usage));
            silo.silo_time = timeStr(siloHours, true);
            if (siloHours < 24) {
                silo.silo_class = 'bg-danger';
            } else if (siloHours < 72) {
                silo.silo_class = 'bg-warning';
            }
            if (siloHours < minHours) {
                minHours = siloHours;
            }
            silo.volume = silo.input ? silo.capacity - silo.qty * silo.content_size : silo.qty * silo.content_size;
            silo.volume = Math.round(silo.volume / 100) / 10;
            if (silo.input) tower.input_volume += silo.volume;
            else tower.output_volume += silo.volume;
        } else {
            silo.silo_time = silo.percent + "%";
        }
        if (silo.name === silo.silo_type_name) {
            silo.name = null;
        }
    });
    if (tower.guns) {
        tower.empty_guns = 0;
        tower.guns.forEach(function(gun) {
            if (gun.qty == 0) tower.empty_guns += 1;
        });
        if (tower.empty_guns > 0) {
            tower.errors.push('Tower has ' + tower.empty_guns + ' guns without ammo.');
        }
    }
    tower.hours_remaining = minHours;
    tower.fuel_volume = tower.fuel_bay_capacity - tower.fuel_qty * 5;
    tower.fuel_volume = Math.round(tower.fuel_volume / 100) / 10;
    tower.input_volume += tower.fuel_volume;
    tower.input_volume = Math.round(tower.input_volume * 10) / 10;
}

posmonControllers.controller('TowerController', ['$scope', '$routeParams', '$location', 'Tower',
        function ($scope, $routeParams, $location, Tower) {
  $scope.round = Math.round;
  Tower.get({towerId: $routeParams.towerId}, function(tower) {
      processTower(tower);
      $scope.tower = tower;
  });
}]);

posmonControllers.controller('TowersController', ['$scope', '$routeParams', '$location', '$window', 'Tower',
        function($scope, $routeParams, $location, $window, Tower) {
  Tower.query({}, function(towers) {
      corpList = [];
      corpSet = {};
      systemList = [];
      systemSet = {};
      ownerList = [];
      ownerSet = {};
      $scope.towers = [];
      towers.forEach(function(tower) {
          processTower(tower);
          if (!corpSet[tower.corp_id]) {
              corpSet[tower.corp_id] = true;
              corpList.push({ 'id': tower.corp_id, 'name': tower.corp_name, 'ticker': tower.corp_ticker });
          }
          if (!systemSet[tower.system_id]) {
              systemSet[tower.system_id] = true;
              systemList.push({ 'id': tower.system_id, 'name': tower.system_name });
          }
          if (!ownerSet[tower.owner_id]) {
              ownerSet[tower.owner_id] = true;
              ownerList.push({ 'id': tower.owner_id, 'name': tower.owner_name, 'type': tower.owner_type });
          }
          $scope.towers.push(tower);
      });
      byName = function(a, b) {
          if (a.name < b.name) return -1;
          if (a.name > b.name) return 1;
          return 0;
      };
      corpList.sort(byName);
      systemList.sort(byName);
      ownerList.sort(function(a, b) {
          if (a.type === b.type) return byName(a, b);
          if (a.type === 'Alliance') return -1;
          if (b.type === 'Alliance') return 1;
          if (a.type === 'Corp') return -1;
          if (b.type === 'Corp') return 1;
          return 0;
      });
      corpList.splice(0, 0, { 'id': 0, 'name': 'All Corporations', 'ticker': 'ALL' });
      systemList.splice(0, 0, { 'id': 0, 'name': 'All Systems' });
      ownerList.splice(0, 0, { 'id': 0, 'name': 'All Owners', 'type': 'All' });
      $scope.all_towers = towers;
      $scope.corporations = corpList;
      $scope.systems = systemList;
      $scope.owners = ownerList;
      find = function(list, id) {
          res = list[0];
          if (id) {
              list.forEach(function(e) {
                  if (e.id == id || e.name == id || e.ticker == id)
                      res = e;
              });
          }
          return res;
      };
      $scope.selected_corp = find(corpList, $location.search().corp);
      $scope.selected_system = find(systemList, $location.search().system);
      $scope.selected_owner = find(ownerList, $location.search().owner);
      selectTowers = function() {
          corp = $scope.selected_corp;
          system = $scope.selected_system;
          owner = $scope.selected_owner;
          $location.search({
              corp: corp.id === 0 ? null : corp.ticker,
              system: system.id === 0 ? null : system.name,
              owner: owner.id === 0 ? null : owner.name
          });
          $scope.towers = $scope.all_towers.filter(function(tower) {
              return (corp.id == 0 || tower.corp_id == corp.id) &&
                  (system.id == 0 || tower.system_id == system.id) &&
                  (owner.id == 0 || tower.owner_id == owner.id);
          });
      };
      selectTowers();
      $scope.selectCorp = function($event, corp) {
          $scope.selected_corp = corp;
          $scope.corpDropdownOpen = false;
          selectTowers();
      };
      $scope.selectSystem = function($event, system) {
          $scope.selected_system = system;
          $scope.systemDropdownOpen = false;
          selectTowers();
      };
      $scope.selectOwner = function($event, owner) {
          $scope.selected_owner = owner;
          $scope.ownerDropdownOpen = false;
          selectTowers();
      };
      $scope.$on('$routeUpdate', function() {
          $scope.selected_corp = find(corpList, $location.search().corp);
          $scope.selected_system = find(systemList, $location.search().system);
          $scope.selected_owner = find(ownerList, $location.search().owner);
          selectTowers();
      });
      $scope.sortByTime = function() {
          $scope.selected_sort = { predicate: 'hours_remaining', description: 'Sort By Time Remaining' };
      };
      $scope.sortByLocation = function() {
          $scope.selected_sort = { predicate: ['system_name', 'planet', 'moon'], description: 'Sort By Location' };
      };
      $scope.sortByTime();
  }, function(errorResponse) {
      $window.location.reload();
  });
  $scope.navigate = function(id) {
      $location.path('/tower/' + id);
  };
}]);

posmonControllers.controller('NavbarController', ['$scope', '$rootScope', '$location', 'Config', 'Search',
        function($scope, $rootScope, $location, Config, Search) {
  Config.get({}, function(config) {
    $rootScope.alliance_id = config.alliance_id;
    $rootScope.logged_in = config.logged_in;
    if (config.logged_in) {
      console.log('Logged in as ' + config.character_name);
      $rootScope.character_id = config.character_id;
      $rootScope.character_name = config.character_name;
    }
  });
  $scope.searchValue = "";
  $scope.select = function(result) {
      switch (result.type) {
          case 'tower':
              $location.path('/tower/' + result.id);
              break;
      }
  };
  $scope.search = function(value) {
      return Search.query({searchText: value}).$promise;
  };
  $scope.submit = function() {
      if (typeof $scope.searchValue === 'string') {
          Search.query({searchText: $scope.searchValue}, function(results) {
              if (results.length > 0) {
                  $scope.select(results[0]);
              }
          });
      } else if (typeof $scope.searchValue === 'object') {
          $scope.select($scope.searchValue);
      }
  };
  $scope.myTowers = function() {
      if ($location.path() === "/towers") {
          $location.search({ owner: $rootScope.character_id });
      } else {
          $location.url('/towers?owner=' + $rootScope.character_id);
      }
  };
}]);

