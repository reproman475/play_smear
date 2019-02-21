import React, { useState, useEffect } from 'react';
import { withRouter } from 'react-router-dom';
import { Card, Row, Col, Button, Modal, Icon } from 'antd';
import axios from 'axios';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import getErrorString from './utils';

import './WaitingRoom.css';

function removePlayerFromGame(player, gameID, setLoading, removePlayerFromList) {
  setLoading(true);
  axios.delete(`/api/smear/v1/games/${gameID}/player/`,
    { data: { id: player.id } })
    .then((response) => {
      setLoading(false);
      removePlayerFromList(player);
    })
      .catch((error) => {
        console.log(error);
        setLoading(false);
        Modal.error({
          title: "Unable to remove player from game",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });

}

function addPlayerToNewTeam(player, gameID, sourceTeamID, destinationTeamID, setLoading) {
  if (destinationTeamID == "bench") {
    // Moving to bench is removing from previous team
    setLoading(true);
    axios.delete(`/api/smear/v1/games/${gameID}/teams/${sourceTeamID}/member/`,
      { data: { id: player.id } })
      .then((response) => {
        setLoading(false);
      })
      .catch((error) => {
        console.log(error);
        setLoading(false);
        // TODO: force a refresh of team data
        Modal.error({
          title: "Unable to remove player from team",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  } else {
    setLoading(true);
    axios.post(`/api/smear/v1/games/${gameID}/teams/${destinationTeamID}/member/`,
      { id: player.id })
      .then((response) => {
        setLoading(false);
      })
      .catch((error) => {
        console.log(error);
        setLoading(false);
        // TODO: force a refresh of team data
        Modal.error({
          title: "Unable to add player to team",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  }
}

function Player(props) {
  const [loading, setLoading] = useState(false);
  const {player, gameID, removePlayerFromList, removeIsVisible} = props;

  const closeIcon = loading ? "loading" : "close-circle";
  const playerIcon = loading ? "loading" : player.is_computer ? "desktop" : "user";

  return (
    <div style={{
      width: "200px",
      border: "solid",
      borderWidth: "1px",
      marginBottom: "4px",
      padding: "15px",
    }}>
      <Row type="flex">
      <Col span={3}>
        <Icon style={{fontSize: '18px'}} type={playerIcon}/>
      </Col>
      <Col span={18} align="center">
        {player.name}
      </Col>
      {removeIsVisible && (
      <Col span={3}>
        <Icon theme="twoTone" twoToneColor="#eb2f96" style={{cursor: "pointer", fontSize: '18px'}} disabled={loading} type={closeIcon} onClick={() => removePlayerFromGame(player, gameID, setLoading, removePlayerFromList)}/>
      </Col>
      )}
      </Row>
    </div>
  );
}

// a little function to help us with reordering the result
const reorder = (list, startIndex, endIndex) => {
    const result = Array.from(list);
    const [removed] = result.splice(startIndex, 1);
    result.splice(endIndex, 0, removed);

    return result;
};

/**
 * Moves an item from one list to another list.
 */
function move(source, setSource, destination, setDestination, droppableSource, droppableDestination) {
    const sourceClone = Array.from(source);
    const destClone = Array.from(destination);
    const [removed] = sourceClone.splice(droppableSource.index, 1);

    destClone.splice(droppableDestination.index, 0, removed);

    setSource(sourceClone);
    setDestination(destClone);
}

const getItemStyle = (isDragging, draggableStyle) => ({
    // some basic styles to make the items look a bit nicer
    userSelect: 'none',

    // change background colour if dragging
    background: isDragging ? 'lightgreen' : 'white',

    // styles we need to apply on draggables
    ...draggableStyle
});

const getListStyle = isDraggingOver => ({
    background: isDraggingOver ? 'lightblue' : '#fff',
    minWidth: 248,
    minHeight: 200,
    margin: 5,
});

function addComputerToGame(gameID, setLoading, addPlayer) {
    setLoading(true);
    axios.post(`/api/smear/v1/games/${gameID}/player/`)
      .then((response) => {
        setLoading(false);
        addPlayer(response.data);
      })
      .catch((error) => {
        console.log(error);
        setLoading(false);
        Modal.error({
          title: "Unable to add computer to game",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  
}

function AddComputer(props) {
  const { gameID, addPlayer } = props;
  const [loading, setLoading] = useState(false);

  const icon = loading ? "loading" : "plus";

  return (
    <Button style={{width: "100%"}} disabled={loading} onClick={() => addComputerToGame(gameID, setLoading, addPlayer)}><Icon type={icon} /> Computer Player</Button>
  );
}

function TeamHolder(props) {
  const {players, gameID, removePlayerFromList, removeIsVisible} = props;
  return players.map((item, index) => (
    <Draggable
      key={item.id}
      draggableId={item.id}
      index={index}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.draggableProps}
            {...provided.dragHandleProps}
            style={getItemStyle(
              snapshot.isDragging,
              provided.draggableProps.style
            )}>
            <Player player={item} gameID={gameID} removePlayerFromList={removePlayerFromList} removeIsVisible={removeIsVisible}/>
          </div>
        )}
    </Draggable>
  ))
}

function startGame(teams, gameID, setLoading, setReload) {
  setLoading(true);
  axios.post(`/api/smear/v1/games/${gameID}/start/`)
    .then((response) => {
      setReload(true);
      setLoading(false);
    })
    .catch((error) => {
      console.log(error);
      setLoading(false);
      Modal.error({
        title: "Unable to start game",
        content: getErrorString(error.response.data),
        maskClosable: true,
      })
    });
}

function initialPlayerAssignment(bench, setBench, teams, players) {
  const initialTeams = Object.entries(teams).reduce((accum, [teamID, items]) => {
    if (!(teamID in accum)) {
      accum[teamID] = []
    }
    return accum;
  }, {});

  const teamsAndPlayers = players.reduce((accum, player) => {
    if (player.team) {
      accum[player.team] = [...accum[player.team], player];

      // Side effect: remove the player from our copy of the bench
      bench.splice(bench.indexOf(player), 1);
    }
    return accum;
  }, initialTeams);

  Object.entries(teamsAndPlayers).forEach(([teamID, teamList]) => {
    teams[teamID].setList(teamList);
  });

  setBench(bench);
}

function WaitingRoom(props) {
  const [allPlayers, setAllPlayers] = useState([]);
  const [bench, setBench] = useState([]);
  // Build a dict that looks like
  // {
  //   team_id: {
  //     list: <state list>,
  //     setList: <state set list>
  //   }
  // }
  const teams = props.game.teams.reduce((accum, team) => {
    const [list, setList] = useState([]);
    accum[team.id] = {
      list: list,
      setList: setList
    };
    return accum;
  }, {});

  const teamSetters = props.game.teams.reduce((accum, team) => {
    accum[team.id] = teams[team.id].setList;
    return accum;
  }, {});

  const teamLists = props.game.teams.reduce((accum, team) => {
    accum[team.id] = teams[team.id].list;
    return accum;
  }, {});

  const playerListSetters = {
    bench: setBench,
    ...teamSetters
  };

  const playerList = {
    bench: bench,
    ...teamLists
  }

  function removePlayer(list, setList, player) {
    const index = list.indexOf(player)
    if (index !== -1) {
      var listCopy = list.slice();
      listCopy.splice(index, 1);
      setList(listCopy);
    }
    const allIndex = allPlayers.indexOf(player)
    if (allIndex !== -1) {
      var allPlayersCopy = allPlayers.slice();
      allPlayersCopy.splice(allIndex, 1);
      setAllPlayers(allPlayersCopy);
    }
  }

  function addPlayer(player) {
    setBench([...bench, player]);
    setAllPlayers([...allPlayers, player]);
  }

  function resetPlayers(gameID, setLoading) {
    setLoading(true);
    axios.delete(`/api/smear/v1/games/${gameID}/teams/all/`)
      .then((response) => {
        setLoading(false);
        initialPlayerAssignment(allPlayers, setBench, teams, response.data.players);
      })
      .catch((error) => {
        console.log(error);
        setLoading(false);
        Modal.error({
          title: "Unable to reset teams",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  }

  function autoAssign(gameID, setLoading) {
    setLoading(true);
    axios.post(`/api/smear/v1/games/${gameID}/teams/all/`)
      .then((response) => {
        setLoading(false);
        initialPlayerAssignment(bench, setBench, teams, response.data.players);
      })
      .catch((error) => {
        console.log(error);
        setLoading(false);
        Modal.error({
          title: "Unable to auto assign players to teams",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  }

  // Adds new players who have joined the game to the bench,
  // and removes players who have left the game
  useEffect(() => {
    const playersToRemove = allPlayers.filter((player) => {
      return props.game.players.indexOf(player) === -1;
    });
    const playersToAddToBench = props.game.players.filter((player) => {
      return allPlayers.indexOf(player) === -1;
    });
    setAllPlayers(props.game.players);
    var benchWithPlayersRemoved = bench.slice();
    for (var i = 0; i < playersToRemove.length; i++) {
      const playerIndex = benchWithPlayersRemoved.indexOf(playersToRemove[i])
      if (playerIndex !== -1) {
        benchWithPlayersRemoved.splice(playerIndex, 1);
      }
    }
    const newBench = [...benchWithPlayersRemoved, ...playersToAddToBench];
    setBench(newBench);

    initialPlayerAssignment(newBench, setBench, teams, props.game.players);
  }, props.game.players);
  
  // If in a multiplayer game, always refresh the game to check for changes
  // Otherwise we don't need to
  useEffect(() => {
    props.setReload(!props.game.single_player);
  }, [props.game.single_player]);

  function onDragEnd(result) {
    const { source, destination } = result;

    // dropped outside the list
    if (!destination) {
      return;
    }

    if (source.droppableId === destination.droppableId) {
      const items = reorder(
        playerList[source.droppableId],
        source.index,
        destination.index
      );

      playerListSetters[source.droppableId](items);

    } else {
      const player = playerList[source.droppableId][source.index];
      const sourceTeamID = source.droppableId;
      const destinationTeamID = destination.droppableId;
      addPlayerToNewTeam(
        player,
        props.game.id,
        sourceTeamID,
        destinationTeamID,
        props.loading,
      );
      move(
        playerList[source.droppableId],
        playerListSetters[source.droppableId],
        playerList[destination.droppableId],
        playerListSetters[destination.droppableId],
        source,
        destination
      );
    }
  };

  const teamDroppables = props.game.teams.map((team, index) => (
    <Col key={index}>
      <Droppable droppableId={""+team.id}>
        {(provided, snapshot) => (
          <Card
            title={team.name}
            headStyle={{backgroundColor: "#f0f5f0" }}
            className="teamCard"
            style={getListStyle(snapshot.isDraggingOver)}
          >
            <div ref={provided.innerRef} style={{minHeight: 200}}>
              <TeamHolder
                players={teams[team.id].list}
                gameID={props.game.id}
                removePlayerFromList={(player) => removePlayer(teams[team.id].list, teams[team.id].setList, player)}
              />
              {provided.placeholder}
            </div>
          </Card>
        )}
      </Droppable>
    </Col>
  ));

  const dnd = (
    <DragDropContext onDragEnd={onDragEnd}>
      <Row type="flex">
        <Col>
          <Droppable droppableId="bench">
            {(provided, snapshot) => (
              <Card
                title="Players"
                headStyle={{backgroundColor: "#f0f5f0" }}
                className="teamCard"
                style={getListStyle(snapshot.isDraggingOver)}
              >
                <div ref={provided.innerRef} style={{minHeight: 200}}>
                  <TeamHolder
                    players={bench}
                    gameID={props.game.id}
                    removePlayerFromList={(player) => removePlayer(bench, setBench, player)}
                    removeIsVisible={true}
                  />
                  <AddComputer gameID={props.game.id} addPlayer={addPlayer}/>
                  {provided.placeholder}
                </div>
              </Card>
            )}
          </Droppable>
        </Col>
        {teamDroppables}
      </Row>
    </DragDropContext>
  );

  return (
    <div className="WaitingRoom">
      <span style={{fontSize: '18px'}}>
      <b>Welcome to game <i>{props.game.name}. </i></b> 
      </span>
      <span>
      Currently assigning teams.
      </span>
      {dnd}
      <div className="flex">
        <Button onClick={() => startGame(teams, props.game.id, props.loading, props.setReload)}>Start Game</Button>
        { props.game.teams.length > 0 &&
          <>
            <Button onClick={() => autoAssign(props.game.id, props.loading)}>Auto Assign</Button>
            <Button onClick={() => resetPlayers(props.game.id, props.loading)}>Reset</Button>
          </>
        }
      </div>
    </div>
  );
}

export default withRouter(WaitingRoom);