###########################################################################
###########################################################################
## A general implementation of a genetic optimisation algorithm.         ##
##                                                                       ##
## Copyright (C)  2022  Oliver Michael Kamperis                          ##
## Email: o.m.kamperis@gmail.com                                         ##
##                                                                       ##
## This program is free software: you can redistribute it and/or modify  ##
## it under the terms of the GNU General Public License as published by  ##
## the Free Software Foundation, either version 3 of the License, or     ##
## any later version.                                                    ##
##                                                                       ##
## This program is distributed in the hope that it will be useful,       ##
## but WITHOUT ANY WARRANTY; without even the implied warranty of        ##
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          ##
## GNU General Public License for more details.                          ##
##                                                                       ##
## You should have received a copy of the GNU General Public License     ##
## along with this program. If not, see <https://www.gnu.org/licenses/>. ##
###########################################################################
###########################################################################

"""General implementation of a genetic optimisation algorithm."""

from abc import ABCMeta, abstractmethod
import dataclasses
import enum
from fractions import Fraction
from functools import cached_property
import functools
import itertools
import math
from numbers import Real
from random import getrandbits as randbits
from typing import Any, Callable, Generic, Iterable, Iterator, Literal, Optional, Type, TypeVar
from numpy import isin, right_shift
from numpy.random import choice, randint, random_integers, Generator, default_rng

from auxiliary.ProgressBars import ResourceProgressBar
from auxiliary.moreitertools import chunk, cycle_for, getitem_zip, max_n

## Need to be able to deal with degree of mutation based on the range.
## For arbitrary bases, this will be based on the order of the possible values in the base.

## How will we deal with constraints like those that will be needed for the membership functions in the fuzzy controllers where the values must be in ascending order?
## Can we use multiple chromosomes to encode: membership function limits, rule outputs, and module gains?

## Numerical gene base type.
NT = TypeVar("NT", bound=Real)

## Generic gene base type (used for arbitrary base types).
GT = TypeVar("GT")

## Generic chromosome type (i.e. genotype).
CT = TypeVar("CT", str, list)

## Generic solution type (i.e. phenotype).
ST = TypeVar("ST")

class GeneBase(Generic[CT], metaclass=ABCMeta):
    """Base class for gene base types."""
    
    @abstractmethod
    def random_chromosomes(self, length: int, quantity: int) -> list[CT]:
        """Return the given quantity of random chromosomes of the given length."""
        ...
    
    @abstractmethod
    def random_genes(self, quantity: int) -> list[GT]:
        """Return the given quantity of random genes."""
        ...

@dataclasses.dataclass(frozen=True) ## TODO: Change to a normal class, take "bin", "hex", or "oct" as argument.
class BitStringBase(GeneBase[str]):
    """
    Represents a bit-string gene base type.
    
    Genes can take only integer values between;
    0 and 2^bits-1 encoded in the given numerical base.
    
    Fields
    ------
    `name: str` - The name of the base type.
    
    `format_: str` - The string formatter symbol for
    converting from binary to the given numerical base type.
    
    `bits: int` - The number of bits needed to represent one gene.
    
    Properties
    ----------
    `values: int` - The number of possible values for one gene.
    
    `values_range: tuple[str]` - The possible values for one gene.
    
    Methods
    -------
    `chromosome_bits: (length: int) -> int` - Return the number of bits needed to represent a chromosome of the given length.
    
    `random_chromosomes: (length: int) -> str` - Return a random chromosome of the given length.
    """
    
    name: str
    format_: str
    bits: int
    
    def __str__(self) -> str:
        """Return the name of the base type and the number of bits per gene."""
        return f"{self.__class__.__name__} :: {self.name}, values: {self.values}, bits/gene: {self.bits}"
    
    @cached_property
    def total_values(self) -> int:
        """Return the number of values a gene can take for the given base type."""
        return 1 << self.bits
    
    @cached_property
    def all_values(self) -> tuple[str, ...]:
        """Return the range of possible values a gene can take for the given base type in ascending order."""
        return tuple(format(v, self.format_) for v in range(self.total_values))
    
    def chromosome_bits(self, length: int) -> int:
        """Return the number of bits needed to represent a chromosome of the given length."""
        return self.bits * length
    
    def random_chromosomes(self, length: int, quantity: int) -> list[str]:
        """Return the given quantity of random chromosomes of the given length."""
        return [format(randbits(self.chromosome_bits(length)), self.format_).zfill(length) for _ in range(quantity)]
    
    def random_genes(self, quantity: int) -> list[str]:
        """Return the given quantity of random genes."""
        return [format(randbits(self.bits), self.format_) for _ in range(quantity)]

@enum.unique
class BitStringBaseTypes(enum.Enum):
    """
    The standard gene base types for 'bit-string' choromsome encodings.
    
    Items
    -----
    `bin = GeneBase("binary", 'b', 1)` - A binary string represenation.
    This uses "base two", i.e. there are only two values a gene can take.
    
    `oct = GeneBase("octal", 'o', 3)` - An octal string representation.
    This uses "base eight", i.e. there are eight possible values a gene can take.
    
    `hex = GeneBase("hexadecimal", 'h', 4)` - A hexadecimal representation.
    This uses "base sixteen", i.e. there are sixteen possible values a gene can take.
    """
    
    bin = BitStringBase("binary", 'b', 1)
    oct = BitStringBase("octal", 'o', 3)
    hex = BitStringBase("hexadecimal", 'x', 4)

@dataclasses.dataclass(frozen=True)
class NumericalBase(GeneBase[list], Generic[NT]):
    """
    Represents an numerical base type.
    
    Genes can take any value from a given range.
    """
    
    name: str
    type_: Type[Real]
    min_range: NT
    max_range: NT
    
    def __post_init__(self) -> None:
        """Check that the given range is valid."""
        if self.min_range >= self.max_range:
            raise ValueError(f"Minimum of range must be less than maximum of range. Got; {self.min_range=} and {self.max_range=}.")
    
    def random_chromosomes(self, length: int, quantity: int) -> list[list[NT]]:
        """Return the given quantity of random chromosomes of the given length."""
        return chunk(random_integers(self.min_range, self.max_range, length * quantity), length, quantity, as_type=list)
    
    def random_genes(self, quantity: int) -> list[NT]:
        """Return the given quantity of random genes."""
        return random_integers(self.min_range, self.max_range, quantity).tolist()

@dataclasses.dataclass(frozen=True)
class ArbitraryBase(GeneBase[list], Generic[GT]):
    """
    Represents an arbitrary base type.
    
    Genes can take any value from a given set of values.
    """
    
    name: str
    values: tuple[GT]
    
    def __str__(self) -> str:
        """Return the name of the base type and the number of bits per gene."""
        return (f"{self.__class__.__name__} :: Values (total = {len(self.values)}): "
                + ", ".join(str(v) for v in self.values[:min(len(self.values, 5))])
                + (", ..." if len(self.values) > 5 else ""))
    
    def random_chromosomes(self, length: int, quantity: int) -> list[list[GT]]:
        """Return the given quantity of random chromosomes of the given length."""
        return chunk(choice(self.values, length * quantity), length, quantity, as_type=list)
    
    def random_genes(self, quantity: int) -> list[GT]:
        """Return the given quantity of random genes."""
        return choice(self.values, quantity).tolist()



class GeneticEncoder(Generic[ST], metaclass=ABCMeta):
    """
    Base class for genetic encoders.
    
    A genetic encoder can encode and decode a candidate solution to and from a chromosome (a sequence of genes).
    A candidiate solution is often referred to as a phenotype and its encoding as a chromosome as a genotype.
    The encoder must also define a fitness evaluation function, which is specific to the encoding.
    Where a fitness value defines the quality of the candidate solution.
    
    There is an important relation between the genetic encoding used, the fitness evaluation function and the
    other genetic operators involved in the algorithm; the recombinator, mutator and selector.
    The designer must ensure that the operators are compatible with the encoding, such that
    operators that modify chromosomes promotes an increase in fitness and generate valid solutions.
    """
    
    def __init__(self,
                 chromosome_length: int = 8,
                 chunks: int | None = None,
                 base: BitStringBaseTypes | Literal["bin", "oct", "hex"] | list[GT] | ArbitraryBase = "bin", ## TODO
                 ) -> None:
        """Create a genetic encoder with a given gene length and base type."""
        self.__chromosome_length: int = chromosome_length
        if not isinstance(base, str):
            self.__base = BitStringBaseTypes[base].value
        elif isinstance(base, BitStringBaseTypes):
            self.__base = base.value
        elif isinstance(base, list):
            self.__base = ArbitraryBase("arbitrary", base)
        elif isinstance(base, ArbitraryBase):
            self.__base = base
        else: raise TypeError(F"Unknown base; {base} of type {type(base)}. Expected one of: BitStringBase, str, list, ArbitraryBase.")
    
    @property
    def chromosome_length(self) -> int:
        """Return the length of a chromosome."""
        return self.__chromosome_length
    
    @property
    def base(self) -> GeneBase:
        """Return the base type of a chromosome."""
        return self.__base
    
    @abstractmethod
    def encode(self, solution: ST) -> CT:
        """Return the solution encoded as a chromosome."""
        raise NotImplementedError
    
    @abstractmethod
    def decode(self, chromosome: CT) -> ST:
        """Return the solution represented by the given chromosome."""
        raise NotImplementedError
    
    @abstractmethod
    def evaluate_fitness(self, chromosome: CT) -> Real:
        """Return the fitness of the given chromosome."""
        raise NotImplementedError



class GeneticRecombinator(metaclass=ABCMeta):
    """
    Base class for genetic recombination operators.
    
    A genetic recombinator selects and swaps genes between two 'parent' chromosomes,
    in order to create two new 'offspring' chromosomes, each of which is some combination of the parents.
    
    A genetic recombinator is agnostic to the representation scheme and encoding used for chromosomes to solutions.
    This is because they only consider the sequence of genes (i.e. their order/position), not the encoding.
    
    In non-permutation recombinators, the offspring chromosomes may not be permutations of the parents.
    Swapped genes or genes sub-sequences should be between those in the same positions in the chromosome.
    
    In permutation recombinators, the offspring chromosomes must be permutations of the parents.
    In non-perfect permutation recombinators, the offspring chromosomes may not be valid solutions.
    
    See: https://en.wikipedia.org/wiki/Recombination_(genetic_algorithm)
    """
    
    @abstractmethod
    def recombine(self, chromosome_1: CT, chromosome_2: CT) -> Iterable[CT]:
        raise NotImplementedError

class PointCrossOver(GeneticRecombinator):
    def recombine(self, chromosome_1: CT, chromosome_2: CT) -> Iterable[CT]:
        ## Choose a sub-sequence (in the same place) using two "points", and swap them between the genes.
        left_point = randint(0, len(chromosome_1))
        right_point = randint(left_point, len(chromosome_1))
        return ((chromosome_1[:left_point] + chromosome_2[left_point:right_point] + chromosome_1[right_point:]),
                (chromosome_2[:left_point] + chromosome_1[left_point:right_point] + chromosome_2[right_point:]))

class SplitCrossOver(GeneticRecombinator):
    """
    Splits a pair of chromosomes into two sub-sequences in the same place, and swaps the pieces between those chromosomes.
    """
    def recombine(self, chromosome_1: CT, chromosome_2: CT) -> Iterable[CT]:
        ## Split the genes in half with a sinlge "point" (in the same place), and swap the sub-sequences.
        point: int = randint(0, len(chromosome_1))
        return ((chromosome_1[:point] + chromosome_2[point:]),
                (chromosome_2[:point] + chromosome_1[point:]))

class UniformSwapper(GeneticRecombinator):
    def recombine(self, chromosome_1: CT, chromosome_2: CT) -> Iterable[CT]:
        """
        For each gene in the chromosomes, randomly select a gene from the first or the second gene, to build a new one.
        """
        new_chromosome_1: list = []
        new_chromosome_2: list = []
        for chromosome_1, chromosome_2 in zip(chromosome_1, chromosome_2):
            if randint(0, 2):
                new_chromosome_1.append(chromosome_1)
                new_chromosome_2.append(chromosome_2)
            else:
                new_chromosome_1.append(chromosome_2)
                new_chromosome_2.append(chromosome_1)
        if isinstance(chromosome_1, str):
            return ("".join(new_chromosome_1), "".join(new_chromosome_2))
        return new_chromosome_1, new_chromosome_2



class GeneticMutator(metaclass=ABCMeta):
    """
    Base class for genetic mutation operators.
    
    A mutator is the genetic operator that promotes diversity in a population
    of possible candidate solutions by randomly modifying the genes of a chromosome.
    A mutator therefore encourages exploration of the search space,
    by causing the population to spread across a larger area of the search space,
    and evaluate new possible candidate solutions that may be closer to the
    optimum than the existing solutions in the population.
    In contrast to recombinators, mutators focus on local search,
    since they cause relatively small changes in the chromosome
    and therefore small movements in the search space.
    Optimisation based on mutation is a relatively slow process compared to recombination.
    
    It is therefore one of the fundamental operators in causing evolution (i.e. change) in a population,
    and allowing a genetic algorithm to improve the fitness (i.e. quality)
    of the candidate solutions in that population, towards finding the glocal optimum.
    
    In theory, mutation also helps prevent a genetic algorithm from getting stuck in local optima,
    by ensuring the population does not become too similar to each other,
    thus slowing convergence to the global optimum, and discouraging exploitation.
    
    Sub-classing
    ------------
    
    The class provides a generic method `mutate`, which if overridden in sub-classes must
    be able to handle any genetic base type.
    
    If the designer however wishes the mutator to treat 'bit-string' and arbitrary
    bases differently, two seperate specialised methods can be overridden instead;
        - `numeric_mutate` any of the standard numeric 'bit-string' bases; binary, octal, hexadecimal,
        - `arbitrary_mutate` any other arbitrary base over some fixed alphabet,
    
    By default, these just call the standard mutate method.
    
    As such, to sub-class genetic mutator, one must override either;
        - the generic mutate method (and possibly any of the specialised mutate methods),
        - or both of the specialised mutatre methods and not the generic mutate method.
    """
    
    def mutate(self, chromosome: CT, base: GeneBase) -> CT:
        """Mutate the given chromosome encoded in the given base."""
        return NotImplemented
    
    def bitstring_mutate(self, chromosome: str, base: BitStringBase) -> str:
        """Mutate the given chromosome encoded in the given bit-string base."""
        return self.mutate(chromosome, base)
    
    def numerical_mutate(self, chromosome: str, base: NumericalBase[NT]) -> list[NT]:
        """Mutate the given chromosome encoded in the given numeric base."""
        return self.mutate(chromosome, base)
    
    def arbitrary_mutate(self, chromosome: list[Any], base: ArbitraryBase[GT]) -> list[GT]:
        """Mutate the given chromosome encoded in the given arbitrary base."""
        return self.mutate(chromosome, base)

class PointMutator(GeneticMutator):
    """
    A point mutator.
    
    Randomly selects one or more genes in a chromosome (with uniform probability),
    and changes their values to a different random value.
    
    In a binary base representation, this simply flips them to the opposite value.
    
    Point mutators are not appropriate for permutation problems, as they may commonly produce invalid solutions.
    """
    
    def __init__(self, points: int) -> None:
        """
        Insert the random new genes into the chromosome at random positions.
        
        Parameters
        ----------
        `points: int` - The number of genes in the chromosome to mutate.
        """
        if not isinstance(points, int) or points < 1:
            raise ValueError("Number of points must be an integer greater than zero. "
                             f"Got; {points} of type {type(points)}.")
        self.__points: int = points
    
    def mutate(self, chromosome: CT, base: GeneBase) -> CT:
        """Point mutate the given chromosome encoded in the given base."""
        for index, gene in zip(randint(len(chromosome), size=self.__points), ## TODO: change to using generator, add generator to base class.
                               base.random_genes(self.__points)):
            chromosome[index] = gene
            # chromosome = chromosome[:index] + gene + chromosome[index+1:]
        return chromosome
    
    def bitstring_mutate(self, chromosome: str, base: BitStringBase) -> str:
        return "".join(self.mutate(list(chromosome), base))

class SwapMutator(GeneticMutator):
    """
    Swap the values of random pairs of genes in the chromosome.
    
    Pick two different genes at random (with uniform probability distribution), and swap their values.
    This is common in permutation based encodings, where the set of values need to be preserved, but the order can be changed.
    
    Swap mutators are appropriate for permutation problems as they always produce valid solutions (given the input is also valid).
    
    # In Swap Mutation we select two genes from our chromosome and interchange their values.
    """
    

class ShuffleMutator(GeneticMutator):
    """
    Pick two different genes at random (with uniform probability), and shuffle (with uniform probability) the sub-sequence of values between them.
    
    A contiguous sub-sequence of genes is randomly selected, and their values are randomly shuffled.
    
    A sub-sequence of a random length (chosen from a given probability density function),
    and a start point of the sub-sequence (chosen with uniform probability).
    
    # In Scramble Mutation we select a subset of our genes and scramble their value. The selected genes may not be contiguous (see the second diagram).
    """
    

class InversionMutator(GeneticMutator):
    """
    Pick two different genes at random (with uniform probability distribution), and invert the sub-sequence of values between them.
    
    Similar to shuffle, except invert (flip, or pivot around its center) the sub-sequence instead of performing the expensive shuffle operation.
    This still disrupts the order, but mostly preserves adjacency of gene values (within the sub-sequence only).
    
    # In Inversion Mutation we select a subset of our genes and reverse their order. The genes have to be contiguous in this case (see the diagram).
    """
    



class GeneticSelector(metaclass=ABCMeta):
    """
    Base class for genetic selection operators.
    
    Selection operators expose two functions;
        - A select method of selecting a subset of a population of candidate solutions
          to be used for culling and reproduction to generate the next generation,
        - A scale method of scaling the fitness of the candidate solutions in the population.
    """
    
    __slots__ = ("__requires_sorted",
                 "__generator")
    
    def __init__(self, requires_sorted: bool, rng: Generator | int | None = None) -> None:
        """
        Super constructor for selection operators.
        
        Parameters
        ----------
        `requires_sorted: bool` - Whether the fitness values of the chromosomes must be sorted in ascending order.
        
        `rng: Generator | int | None` - Either an random number generator instance,
        or a seed for the selector to create its own, None generates a random seed.
        """
        self.__requires_sorted: bool = requires_sorted
        if isinstance(rng, Generator):
            self.__generator: Generator = rng
        self.__generator: Generator = default_rng(rng)
    
    @property
    def requires_sorted(self) -> bool:
        """Whether the selector requires the fitness values to be sorted in ascending order."""
        return self.__requires_sorted
    
    @property
    def generator(self) -> Generator:
        """Get the random number generator used by the selector."""
        return self.__generator
    
    @abstractmethod
    def select(self,
               population: list[CT],
               fitness: list[Real],
               quantity: int
               ) -> list[CT]:
        """Select the given number of chromosomes from the population."""
        ...
    
    def scale(self,
              fitness: list[Real]
              ) -> list[Real]:
        """Scale the given fitness values."""
        return fitness
    
    @staticmethod
    def validate(population: list[CT], fitness: list[Real], quantity: int) -> None:
        """Validate arguments for the selection operator."""
        if len(population) != len(fitness):
            raise ValueError("Population and fitness values must be the same length.")
        if quantity < 1:
            raise ValueError("Quantity of chromosomes to select must be greater than zero.")

class ProportionateSelector(GeneticSelector):
    """Selects chromosomes from a population with probability proportionate to fitness with replacement."""
    
    def __init__(self) -> None:
        """Create a new proportionate selector."""
        super().__init__(requires_sorted=False)
    
    def select(self,
               population: list[CT],
               fitness: list[Real],
               quantity: int
               ) -> list[CT]:
        """Select a given quantity of chromosomes from the population with probability proportionate to fitness with replacement."""
        return tuple(getitem_zip(self.generator.choice(getitem_zip(population, fitness), quantity, p=fitness)))

class RankedSelector(GeneticSelector):
    """Selects chromosomes from a population with probability proportionate to fitness rank with replacement."""
    
    def __init__(self) -> None:
        """Create a new ranked selector."""
        super().__init__(requires_sorted=True)
    
    def select(self,
               population: list[CT],
               fitness: list[Real],
               quantity: int
               ) -> list[CT]:
        """Select a given quantity of chromosomes from the population with probability proportionate to fitness rank with replacement."""
        pop_size: int = len(population)
        rank_sum: float = (pop_size + 1) * (pop_size / 2.0) 
        ranks: list[Fraction] = [Fraction(i / rank_sum) for i in range(pop_size)]
        return tuple(getitem_zip(self.generator.choice(getitem_zip(population, fitness), quantity, p=ranks)))

class TournamentSelector(GeneticSelector):
    """
    Class defining tournament selectors.
    
    Tournament selection selects chromosomes from a population by
    pitching them against each other in competitions called tournaments.
    
    Individuals are selected for inclusion in tournaments with uniform probability
    with replacement, and the tournamenet winner(s) are selected either by;
    choosing the highest fitness individual(s), or randomly with probability
    either proportionate to fitness or ranked fitness.
    """
    
    def __init__(self,
                 tournamenet_size: int = 3,
                 n_chosen: int = 1,
                 inner_selector: ProportionateSelector | RankedSelector | None = None
                 ) -> None:
        """
        Create a new tournament selector.
        
        Selecting either the best or proportionate to fitness or fitness rank.
        """
        if tournamenet_size < 2:
            raise ValueError(f"Tournament size must be greater than one. Got; {tournamenet_size}")
        if not n_chosen < tournamenet_size:
            raise ValueError("Number of chosen chromosomes must be less than the tournament size. "
                             f"Got; {tournamenet_size=}, {n_chosen=}.")
        super().__init__(requires_sorted=(inner_selector is None or inner_selector.requires_sorted))
        self.__tournament_size: int = tournamenet_size
        self.__n_chosen: int = n_chosen
        self.__inner_selector: ProportionateSelector | RankedSelector | None = inner_selector
    
    def select(self, population: list[CT], fitness: list[Real], quantity: int) -> list[CT]:
        """
        Select a given quantity of chromosomes from the population by pitching them against each other in tournaments.
        
        Chromosomes selected for tournamenets are selected with uniform probability with replacement.
        """
        tournaments = chunk(self.generator.choice(getitem_zip(population, fitness),
                                                  self.__tournament_size * quantity),
                            self.__tournament_size, quantity, as_type=True)
        if self.__inner_selector is None:
            winner_lists = (max_n(tournament, n=self.__n_chosen, key=lambda x: x[1]) for tournament in tournaments)
        winner_lists = (self.__inner_selector.select(*zip(tournament), quantity=self.__n_chosen) for tournament in tournaments)
        return list(itertools.chain.from_iterable(winner_lists))
    
    def scale(self, fitness: list[Real]) -> list[Real]:
        """Scale the given fitness values, by default calling the inner selector's scale method."""
        if self.__inner_selector is not None:
            return self.__inner_selector.scale(fitness)
        return super().scale(fitness)

# class SUSselector(Selector):
#     def __init__(self, requires_sorted_fitness: bool) -> None:
#         """Create a new Stochastic Universal Sampler (SUS) selector."""
#         super().__init__(requires_sorted_fitness)
    
#     def select(self, population: list[Chromosome], fitness: list[Real], quantity: int, generator: Generator) -> list[Chromosome]:
#         """Select a given quantity of chromosomes from the population."""
#         self.validate(population, fitness, quantity)
#         return generator.choice(population, quantity, p=fitness)
#     #         pop_size: int = len(population)
#     #         chunk_size: int = max(min_chunk_size, math.floor(pop_size / quantity))
#     #         selected: list[str] = []
#     #         ## This doesn't actually account for the fitness values.
#     #         while len(selected) != quantity:
#     #             selected.extend(gene for gene in range(0, pop_size, self.__random_generator.choice(chunk_size)))
#     #         return selected



# class SelectorCombiner(Selector):
#     """Can combine multiple selection schemes and transition between using different ones a various stages of the search."""
#     pass



@dataclasses.dataclass(frozen=True)
class GeneticAlgorithmSolution:
    """A solution to a genetic algorithm."""
    
    best_individual: CT
    best_fitness: Fraction
    population: list[CT] ## TODO Order the population such that the highest fitness individuals occur first.
    fitness_values: list[Fraction]
    max_fitness_reached: bool = False
    max_generations_reached: bool = False
    stagnation_limit_reached: bool = False

class GeneticSystem:
    """
    A genetic system.
    
    Genetic Operator
    ----------------
    
    1. Solution Encoder - Representation as chromosomes formed by a sequence of genes.
    
        A solution is called the phenotype,
        and its encoding that the genetic algorithm operates on and evolves is called the genotype.
        
        The decoder function is required, the encoder is optional.
        
        In order to evaluate fitness and to return a best-fit solution at the end,
        the algorithm needs to be able to decode genotypes to phenotypes.
        
        When initialising a problem, one may want to specific an initial set of solutions to evolve,
        to do this the algorithm needs to be able to encode phenotypes to genotypes.
        
        - Numeric representation; binary, octal, or hexadecimal sequence;
            - In binary, the nucleotide bases are; 1 or 2, for example.
            - For some problems, it is difficult to encode a solution in binary,
              you may need to split the chromosome up into mutliple sub-sequences
              to encode different properties of the solution. The quality of the complete
              solution is then the sum of the quality of its parts.
        
        - Identifier list representation - Any sized set of arbitrary identifiers for properties or elements of a solution;
            - The nucleotide bases are any of a set of identifiers; "london", "birmingham", "leeds".
            - Useful when solution length is known, but ordering needs to be optimised.
        
        - Multiple chromosome representation - TODO Is this what EVs do?
    
    2. Selection Scheme and Fitness Function
    
        - Deterministic Selection: Only best n < pop_size reproduce, in this case the fitness function is not necessary.
        - Proportional Seletion: Reproduction chances are proportional to fitness value.
        - Ranked Fitness Selection: Solutions are ranked according to fitness, reproduction chance proportional to fitness.
        - Tournament Selection: Solutions compete against each other, fittest wins and gets to reproduce.
        
        - Elitism in selection:
        - Convergence and diversity biases in selection: Affect selection pressure towards high values of fitness, and thus exploration/exploitation trade-off.
        - Boltzmann decay for biases:
            ...In Boltzmann selection, a continuously varying temperature controls the rate of selection according to a preset schedule. The temperature starts out high, which means that the selection pressure is low. The temperature is gradually lowered, which gradually increases the selection pressure, thereby allowing the GA to narrow in more closely to the best part of the search space while maintaining the appropriate degree of diversity...
    
    3. Genetic Recombinator
    
    
    
    4. Genetic Mutator
    
    
    
    Algorithm procedure/structure
    -----------------------------
    
    1. population initialisation
    
    2. population evaluation
    
    3. stopping condition -> best solution
    
    4. selection
    
    5. crossover
    
    6. mutation
    
    7. population evaluation and update 3
    
    """
    
    __slots__ = (## Functions defining the system's genetic operators.
                 "__encoder",
                 "__recombinator",
                 "__mutator",
                 "__random_generator")
    
    def __init__(self,
                 encoder: GeneticEncoder,
                 selector: GeneticSelector,
                 recombinator: GeneticRecombinator,
                 mutator: GeneticMutator
                 ) -> None:
        
        self.__encoder: GeneticEncoder = encoder
        self.__selector: GeneticSelector = selector
        self.__recombinator: GeneticRecombinator = recombinator
        self.__mutator: GeneticMutator = mutator
        
        self.__random_generator: Generator = default_rng()
    
    @staticmethod
    def linear_decay(diversity_bias: Fraction, decay: Fraction) -> Fraction:
        "Decay according to: `max(0.0, initial_diversity_bias - ((1.0 - bias_decay) * generation))`."
        return max(0.0, diversity_bias - decay)
    
    @staticmethod
    def polynomial_decay(diversity_bias: Fraction, decay: Fraction) -> Fraction:
        "Decay according to: `initial_diversity_bias ^ (generation / (1.0 - bias_decay))`."
        return diversity_bias ** (1.0 / (1.0 - decay))
    
    @staticmethod
    def exponential_decay(diversity_bias: Fraction, decay: Fraction) -> Fraction:
        ## - Diversity bias reduces logarithmically in generations:
        ##  - diversity_bias_at_generation = initial_diversity_bias * ((1 - bias_decay) ^ generation), (equivalent to initial_diversity_bias * (e ^ (decay_constant * generation)) where decay contant is some large negative number)
        ##  - reaches to zero in the limit to infinity
        ## - Convergence bias increases logarithmically in generations:
        ##  - convergence_bias_at_generation = 1 - (initial_diversity_bias * (bias_decay ^ generation)),
        ##  - increases to 1 in the limit to infinity
        "Decay according to: `initial_diversity_bias * ((1.0 - bias_decay) ^ generation)`."
        return diversity_bias * (1.0 - decay)
    
    @staticmethod
    def get_decay_function(decay_type: "DecayType" | Literal["lin", "pol", "exp"]) -> Callable[[Fraction, Fraction], Fraction]:
        if isinstance(decay_type, DecayType):
            return decay_type.value[0]
        return DecayType[decay_type].value[0]
    
    def set_operators(self) -> None:
        ...
    
    def initialise(self) -> None:
        ...
    
    def run(self,
            
            init_pop_size: int,
            max_pop_size: int,
            expansion_factor: Fraction,
            
            # scaling_scheme: Literal["lin", "sigma", "power-law", "boltzmann"],
            selection_scheme: Literal["prop", "rank"], ## "trans-ranked", "tournament", "SUS" : Params for tournament >> tournament_size: int, inner_selection: best | prop | rank | trans-ranked | SUS
            
            ## use_ranked_fitness: bool = False,
            ## best_fit_gets_proportion_of_pie: Fraction = 1,
            ## P_c must be greater than 1/2 (50%) to actually bias it towards better individuals, otherwise if P_c < 0.5 last individual would actually have more chance to to be picked than second to last.
            ## But selection should be proportional to ratio of biases = (convergence_bias / diversity_bias)
            
            survival_factor: Fraction, 
            # survival_factor_rate: Optional[Fraction],
            # survival_factor_rate_type: Optional["DecayType" | Literal["lin", "pol", "exp"]],
            survival_elitism_factor: Optional[Fraction], ## Fraction of the surviving that are the elite.
            # survival_elitism_growth: Optional[Fraction],
            # survival_elitism_growth_type: Optional["DecayType" | Literal["lin", "pol", "exp"]],
            ## survival_filter: Optional[Callable[[Chromosome, Fraction, dict[str, Fraction], Fraction], bool]] = None,
            ##      - Function: (individual, fitness, fitness_statisitcs: statistic_name -> statistic, fitness_threshold) -> survived
            ## Common filters are to choose those x% above the mean or median, or to choose only those within x% of the fitness threshold.
            
            replacement: bool,
            reproduction_elitism_factor: Fraction,
            reproduction_elitism_growth: Fraction,
            reproduction_elitism_growth_type: Optional["DecayType" | Literal["lin", "pol", "exp"]],
            
            mutation_factor: Fraction,
            mutation_factor_growth: Fraction,
            mutation_factor_growth_type: Optional["DecayType" | Literal["lin", "pol", "exp"]],
            mutation_distribution: Literal["uniform", "half_logistic", "trunc_exponential"],
            mutation_step_size: Fraction,
            mutation_step_size_decay: Fraction,
            mutation_step_size_decay_type: Optional["DecayType" | Literal["lin", "pol", "exp"]],
            
            max_generations: Optional[int],
            fitness_threshold: Optional[Fraction],
            fitness_proportion: Optional[Fraction | int],
            stagnation_limit: Optional[int | Fraction],
            stagnation_proportion: Optional[Fraction | int] = 0.10, ## TODO Could use numpy.allclose
            
            ## These are used only for proportional fitness
            diversity_bias: Optional[Fraction] = Fraction(0.95),
            diversity_bias_decay: Optional[int | Fraction] = 100,
            diversity_bias_decay_type: "DecayType" | Literal["lin", "pol", "exp", "hl-exp"] = "exp" # ["threshold-converge", "stagnation-diverge"]
            ##      - converge towards fitness threshold - proportional to difference between mean fitness and fitness threshold,
            ##      - converge on rate of change towards fitness threshold,
            ##      - diverge on stagnation on best fittest towards fitness threshold. Increase proportional to diversity_bias * (stagnated_generations / stagnation_limit). This should try to explore around the solution space when the best fitness gets stuck on a local minima.
            
            ) -> GeneticAlgorithmSolution:
        
        """
        
        Parameters
        ----------
        
        `survival_factor: Fraction` - Survival factor defines how much culling (equal to 1.0 - survival factor) we have, i.e. how much of the population for a given generation does not survive to the reproduction stage, and are not even considered for selection for recombination/reproduction.
        Low survival factor encourages exploitation of better solutions and speeds up convergence, by culling all but the best individuals, and allowing only the best to reproduce and search (relatively) locally to those best.
        
        `survival_factor_rate: Fraction` - 
        
        `survival_factor_change: Literal["decrease", "increase"]` - Usually, if replacement is enabled, it is desirable to start with a high survive factor to promote early exploration of the search space and decrease the factor to promote greater exploitation
        as the search progresses, focusing search towards the very best solutions it has found.
        
        `replacement: bool = True` - Defines whether parents are replaced by their offspring, or the parents survive to the next generation along with their offspring.
        If they are allowed to survive then a survival factor of 1.0 would mean recombination/reproduction would stop happening after reaching the maximum population size.
        If replacement is allowed, then the problem may be that our solutions might actually get worse if our exploration did not go well.
        If the survival factor is high, then reproducing without replacement is a problem, since we get much more limited to how much we can explore the search space and the population approaches its max size,
        so a high survival factor later in the search (when all the solutions are very similar) may discourage exploration (similar to how we want to use creep mutation later in the search to deal with the last little bit of optimisation to reach the exact global optimum).
        
        `stagnation_proportion: Fraction` - If given and not none, return if the average fitness of the best fitting fraction of the population is stagnated (does not increase) for a number of generations equal to the stagnation limit.
        This intuition is that the search should stop only if a "large" proportion of the best quality candidates are not making significant improvement for a "long" time.
        Otherwise, return of the fitness of the best fitting individual is stagenated for the stagnation limit.
        If only the best fitting individual is used as the test of stagnation, it may result in a premature return of the algorithm, when other high fitness individuals would have achieved better fitness that the current maximum if allowed to evolve more
        particularly by creep mutation, which can we time consuming.
        
        `mutation_step_size: Fraction` - The degree of mutation or "step size" (i.e. the amount a single gene can change), change between totally random mutation and creep mutation based on generations or fitness to threshold.
        
        `max_generations: Optional[int]` -
        
        `fitness_threshold: Optional[Fraction]` -
        
        `fitness_proportion: Optional[Fraction | int]` - Return if the average fitness of the best fitness fraction of the population is above the fitness threshold.
        
        `stagnation_limit: Optional[int | Fraction]` - The maximum number of stagnated generations before returning.
        
        `stagnation_proportion: Optional[Fraction | int] = 0.10` -
        
        Stop Conditions
        ---------------
        
        The algorithm runs until one of the following stop conditions has been reached:
        
            - A solution is found that reaches or exceeds the fitness threshold,
            - The maximum generation limit has been reached,
            - The maximum running time or memory usage has been reached,
            - The best fit solutions have stagnated (reached some maxima) such that more generations are not increasing fitness,
              the algorithm may have found the global maxima, or it may be stuck in a logcal maxima.
        
        Notes
        -----
        
        To perform steady state selection for reproduction set;
            - survival_factor = 1.0 - X, where X is fraction of individuals to be culled,
            - survival_elitism_factor = 1.0, such that only the best survive (and the worst are culled) deterministically,
            - disable replacement.
        """
        
        ## TODO Add tqdm, logging, data collection (with pandas?), and data visualisation.
        
        if survival_factor >= Fraction(1.0):
            raise ValueError("Survival factor must be less than 1.0."
                             f"Got; {survival_factor=}.")
        
        if replacement and (expansion_factor * survival_factor) <= 1.0:
            raise ValueError("Population size would shrink or not grow "
                             f"with; {expansion_factor=}, {survival_factor=}."
                             "Their multiple must be greater than 1.0.")
        
        if stagnation_limit is not None and not isinstance(stagnation_limit, int):
            if max_generations is None:
                raise TypeError("Stagnation limit must be an integer if the maximum generations is not given or None."
                                f"Got; {stagnation_limit=} of type {type(stagnation_limit)} and {max_generations=} of {type(max_generations)}.")
            stagnation_limit = int(stagnation_limit * max_generations)
        
        population: list[CT] = self.create_population(init_pop_size)
        fitness_values: list[Fraction] = [self.__encoder.evaluate_fitness(individual)
                                          for individual in population]
        
        ## If elitism is enabled for either selection or mutation then the population and their fitness values need to be ordered.
        if survival_elitism_factor is not None:
            population, fitness_values = zip(*sorted(zip(population, fitness_values),
                                                        key=lambda item: item[1]))
            population = list(population)
            fitness_values = list(fitness_values)
        
        max_fitness, min_fitness = max(fitness_values), min(fitness_values)
        generation: int = 0
        
        ## Variables for checking stagnation
        best_fitness_achieved: Fraction = max_fitness
        stagnated_generations: int = 0
        
        if diversity_bias_decay_type is not None:
            diversity_bias_decay_function = self.get_decay_function(diversity_bias_decay_type)
        if mutation_factor_growth_type is not None:
            mutation_factor_growth_function = self.get_decay_function(mutation_factor_growth_type)
        
        progress_bar = ResourceProgressBar(initial=1, total=max_generations)
        
        while not (generation >= max_generations):
            if diversity_bias is not None:
                ## Update the convergence and diversity biases;
                ##      - Convergence increases by the decay factor,
                ##      - Diversity reduces by the decay factor.
                if diversity_bias_decay is not None and diversity_bias_decay_type is not None:
                    diversity_bias = diversity_bias_decay_function(diversity_bias, diversity_bias_decay)
                
                ## Apply biases to the fitness values;
                ##      - Diversity bias increases low fitness, encouraging exploration,
                ##        Individuals gain fitness directly proportional to diversity bias and how much worse than the maximum fitness.
                fitness_values = [fitness
                                  + ((max_fitness - fitness) * diversity_bias)
                                  for fitness in fitness_values]
            
            ## Applying scaling to the fitness values.
            fitness_values = self.__selector.scale(fitness_values)
            
            base_population_size: int = len(population)
            
            ## Select part of the existing population to survive to the next generation and cull the rest;
            ##      - The selection scheme is random (unless the elitism factor is 1.0) with chance of survival proportional to fitness.
            ##      - This step emulates Darwin's principle of survival of the fittest.
            population, fitness_values = self.cull_population(population, fitness_values, survival_factor, survival_elitism_factor)
            
            ## Recombine the survivors to produce offsrping and expand the population to the lower of;
            ##      - The max population size,
            ##      - increase the size by our maximum expansion factor.
            desired_population_size: int = min(math.ceil(base_population_size * expansion_factor), max_pop_size)
            population = self.grow_population(population, fitness_values, desired_population_size, replacement)
            
            ## Randomly mutate the grown population
            if generation != 0:
                mutation_factor = mutation_factor_growth_function(mutation_factor, mutation_factor_growth)
            mutated_population: list[CT] = self.mutate_population(population, fitness_values, mutation_distribution)
            
            ## Update the population and fitness values with the new generation.
            population = mutated_population
            fitness_values: list[Fraction] = [self.__encoder.evaluate_fitness(individual)
                                              for individual in population]
            
            ## If elitism is enabled the population and their fitness values need to be ordered.
            if survival_elitism_factor is not None:
                population, fitness_values = zip(*sorted(zip(population, fitness_values),
                                                         key=lambda item: item[1]))
                population = list(population)
                fitness_values = list(fitness_values)
                max_individual = population[-1]
                max_fitness = fitness_values[-1]
            else:
                max_fitness_index, max_fitness = max(enumerate(fitness_values), key=lambda item: item[1])
                max_individual = population[max_fitness_index]
                min_fitness = min(fitness_values)
            
            if max_fitness > best_fitness_achieved:
                best_fitness_achieved = max_fitness
                best_individual_achieved = max_individual
            else: stagnated_generations += 1
            
            generation += 1
            progress_bar.update(data={"Best fitness" : str(best_fitness_achieved)})
            
            ## Determine whether the fitness threshold has been reached.
            if best_fitness_achieved >= fitness_threshold:
                return GeneticAlgorithmSolution(best_individual_achieved, best_fitness_achieved, population, fitness_values, max_fitness_reached=True)
            
            ## Determine whether the stagnation limit has been reached.
            if stagnated_generations == stagnation_limit:
                return GeneticAlgorithmSolution(best_individual_achieved, best_fitness_achieved, population, fitness_values, stagnation_limit_reached=True)
        
        return GeneticAlgorithmSolution(best_individual_achieved, best_fitness_achieved, population, fitness_values, max_generations_reached=True)
    
    def create_population(self, population_size: int) -> list[CT]:
        """Create a new population of the given size."""
        total_bits: int = self.__encoder.base.bits * self.__encoder.gene_length
        return [format(randbits(total_bits),
                       self.__encoder.base.format_).zfill(self.__encoder.gene_length)
                for _ in range(population_size)]
    
    def cull_population(self,
                        population: list[CT],
                        fitness_values: list[Fraction],
                        survival_factor: Fraction,
                        elitism_factor: Fraction | None
                        ) -> tuple[list[CT], list[Fraction]]:
        """
        Select individuals from the current population to survive to and reproduce for the next generation.
        Individuals that do not survive are said to be culled from the population and do not get a chance to reproduce and propagate features of their genes to the next generation.
        
        The intuition is that individuals with sufficiently low fitness (relativeo the other individuals in the population) will get out competed by better adapted individuals and therefore will not survive to reproduce offspring.
        The assumption, is that such individuals don't have genes with desirable features, and therefore we don't want them in the gene pool at all.
        
        Reproduction with replacement might be considered similar to population culling and reproduction without replacement,
        however this is not true, since the prior allows low-fitness individuals to dilute the mating pool and allows potentially undesirable genes to remain in gene pool.
        
        A low survival factor results in a more exploitative search and faster convergence,
        since a large proportion of the population is culled, and the search is much more focused on a small set of genes/area of the search space.
        This is particuarly true if the elitism factor is high, because lower fitness indivuduals will have much less chance to reproduce and contribute their genes to future generations,
        and higher fitness individuals will dominate the mating proceedure.
        
        The survival factor decay exists to allow a greater number of individuals to survive to reproduce at earlier generations to promote early exploration,
        but increasingly reducing the number of individuals that survive to increasingly focus the search and exploit the best quality solutions.
        
        Parameters
        ----------
        
        `population: list` -
        
        `fitness_values: list[Fraction]` - 
        If `elitism_factor` is not None, then the fitness values must be sorder in ascending order.
        
        `survival_factor: Fraction` -
        
        `elitism_factor: {Fraction | None}` - 
        """
        ## The current population size and the quantity of them to choose to survive to the next generation.
        population_size: int = len(population)
        survive_quantity: int = math.ceil(population_size * survival_factor)
        
        ## If all individuals in the current population survive then skip the culling phase.
        if population_size == survive_quantity:
            return (population, fitness_values)
        
        ## If elitism factor is not given or None then always choose randomly with probability proportion.
        if elitism_factor is None:
            return self.__selector.select(population, fitness_values, survive_quantity)
        
        ## The quantity of elite individuals that are guaranteed to survive.
        elite_quantity = math.ceil(survive_quantity * elitism_factor)
        
        ## If all surviving are elite, then skip random selection phase,
        ## simply select deterministically the best individuals from the previous generation.
        if survive_quantity == elite_quantity:
            return (population[population_size - survive_quantity:],
                    fitness_values[population_size - survive_quantity:])
        
        ## Non-elite part of the population chosen from randomly to generate competing quantity of survive quantity
        comp_quantity: int = survive_quantity - elite_quantity
        comp_population: list[CT] = population[0:population_size - elite_quantity]
        comp_fitness_values: list[Fraction] = fitness_values[0:population_size - elite_quantity]
        comp_popluation, comp_fitness_values = self.__selector.select(comp_population, comp_fitness_values, comp_quantity)
        
        return (comp_popluation + population[population_size - elite_quantity:],
                comp_fitness_values + fitness_values[population_size - elite_quantity:])
    
    def grow_population(self,
                        population: list[CT],
                        fitness_values: Optional[list[Fraction]],
                        desired_population_size: int,
                        reproduction_elitism_factor: Fraction | None,
                        survival_factor: Fraction,
                        survival_elitism_factor: Fraction = Fraction(0.0), # These are added to `offspring` as an initial stage.
                        # These ones require us to check the individual is not already in the population, use set membership lookup (on index?), remember that it is allowed for the exact same chromosome to exist in the population more than once.
                        ) -> list[CT]:
        """
        Grow the population to the desired size.
        
        Population growth occurs by individuals in the population reproducing
        in randomly chosen pairs of parents with fitness poportional probability
        (with replacement), to produce a pair of offspring. Usually, the parents
        are replaced by their offspring in the grown population, but optionally
        and with fitness poportional probability the parents can also survive
        and remain in the grown population.
        
        Parameters
        ----------
        
        `elitism_factor: Fraction = Fraction(0.0)` - Factor of best
        fitness portion of the population that are guaranteed to reproduce
        assuming that there is space in the population to do so. This is
        done by choosing parent pairs from the reproductive elite set without
        replacement first, as a seperate initial stage of the population growth.
        Once the elite set is consumed, then return to the usual reproduction mechanism.
        """
        offspring: list[CT] = []
        
        ## The current population size and the quantity of them to choose to survive to the next generation.
        population_size: int = len(population)
        survive_quantity: int = math.ceil(population_size * survival_factor)
        
        ## If all individuals in the current population survive then skip the reproduction phase.
        if desired_population_size == survive_quantity:
            return population
        
        ##
        elite_survive_quantity: int = math.ceil(survive_quantity * survival_elitism_factor)
        comp_survive_quantity: int = survive_quantity - elite_survive_quantity
        
        ##
        survived = population[-elite_survive_quantity:]
        survived.extend(self.__selector.select(population[:-elite_survive_quantity],
                                               fitness_values[:-elite_survive_quantity],
                                               comp_survive_quantity))
        offspring.extend(survived)
        
        ##
        offspring_quantity: int = desired_population_size - survive_quantity
        if offspring_quantity == 0:
            return offspring
        
        ## Select parent pairs with uniform probability with replacement.
        total_parents: int = (offspring_quantity + (offspring_quantity % 2))
        elite_reprod_quantity: int = math.ceil(total_parents * reproduction_elitism_factor)
        elite_reprod_quantity += elite_reprod_quantity % 2
        comp_reprod_quantity: int = total_parents - elite_reprod_quantity
        
        ##
        selected = population[-elite_reprod_quantity:]
        selected.extend(self.__selector.select(population[:-elite_reprod_quantity],
                                               fitness_values[:-elite_reprod_quantity],
                                               comp_reprod_quantity))
        parent_pairs: Iterator[tuple[CT, CT]] = chunk(selected, 2, comp_reprod_quantity // 2, as_type=tuple)
        
        ##
        for parent_1, parent_2 in parent_pairs:
            children: list[CT] = self.__recombinator.recombine(parent_1, parent_2)
            max_children: int = min(len(children), offspring_quantity - (len(offspring) - survive_quantity))
            offspring.extend(children[:max_children])
        
        return offspring
    
    def mutate_population(self,
                          population: list[CT],
                          mutation_factor: Fraction = Fraction(1),
                          mutate_all: bool = True
                          ) -> list[CT]:
        """
        Mutate the population.
        
        By default, mutates each individual in the population exactly once.
        If `mutation_factor` is an integer greater than one, then mutate
        each individual a multiple of times equal to the factor.
        If `mutation_factor` is not an integer then randomly choose a number
        of individuals from the population to mutate (with replacement)
        equal to the non-integer part of the factor, i.e. `math.floor(len(population) * (mutation_factor % 1.0))`.
        If `mutate_all` is False then instead randomly choose a number of
        individuals from the population to mutate (with replacement) equal to `math.floor(len(population) * mutation_factor)`.
        """
        ##
        mutations_quantity: int = math.floor(len(population) * mutation_factor)
        mutated_population: list[CT] = population
        
        if isinstance(self.__encoder.base, BitStringBase):
            mutate = self.__mutator.bitstring_mutate
        elif isinstance(self.__encoder.base, NumericalBase):
            mutate = self.__mutator.numerical_mutate
        else:
            mutate = self.__mutator.arbitrary_mutate
        
        if (mutate_all and mutations_quantity >= len(population)):
            cycles: int = mutations_quantity // len(population)
            for index in cycle_for(range(len(population)), cycles):
                mutated_population[index] = mutate(mutated_population[index],
                                                   self.__encoder.base)
            mutations_quantity -= len(population) * cycles
            # else: mutations_quantity %= len(population) ## TODO
        
        if (not mutate_all
            or mutations_quantity != 0):
            for index in self.__random_generator.choice(len(population), mutations_quantity):
                mutated_population[index] = mutate(mutated_population[index],
                                                   self.__encoder.base)
        
        return mutated_population

@enum.unique
class DecayType(enum.Enum):
    lin = (GeneticSystem.linear_decay,)
    pol = (GeneticSystem.polynomial_decay,)
    exp = (GeneticSystem.exponential_decay,)
